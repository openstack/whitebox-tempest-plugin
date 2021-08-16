# Copyright 2016 Red Hat
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import six
import xml.etree.ElementTree as ET

from oslo_log import log as logging
from tempest.api.compute import base
from tempest.common import waiters
from tempest import config
from tempest.lib.common.utils import data_utils
from tempest.lib.common.utils import test_utils

from whitebox_tempest_plugin.services import clients
from whitebox_tempest_plugin import utils as whitebox_utils

if six.PY2:
    import contextlib2 as contextlib
else:
    import contextlib


CONF = config.CONF
LOG = logging.getLogger(__name__)


class BaseWhiteboxComputeTest(base.BaseV2ComputeAdminTest):

    def create_flavor(self, ram=64, vcpus=2,
                      disk=CONF.whitebox.flavor_volume_size, name=None,
                      is_public='True', extra_specs=None, **kwargs):
        flavor = super(BaseWhiteboxComputeTest, self).create_flavor(
            ram, vcpus, disk, name, is_public, **kwargs)
        if extra_specs:
            self.os_admin.flavors_client.set_flavor_extra_spec(flavor['id'],
                                                               **extra_specs)
        return flavor

    def copy_default_image(self, **kwargs):
        """Creates a new image by downloading the default image's bits and
        uploading them to a new image. Any kwargs are set as image properties
        on the new image.

        :return image_id: The UUID of the newly created image.
        """
        image = self.images_client.show_image(CONF.compute.image_ref)
        image_data = self.images_client.show_image_file(
            CONF.compute.image_ref).data
        image_file = six.BytesIO(image_data)

        create_dict = {
            'container_format': image['container_format'],
            'disk_format': image['disk_format'],
            'min_disk': image['min_disk'],
            'min_ram': image['min_ram'],
        }
        create_dict.update(kwargs)
        new_image = self.images_client.create_image(**create_dict)
        self.addCleanup(self.images_client.delete_image, new_image['id'])
        self.images_client.store_image_file(new_image['id'], image_file)

        return new_image['id']

    def list_compute_hosts(self):
        """Returns a list of all nova-compute hostnames in the deployment.
        Assumes all are up and running.
        """
        services = self.os_admin.services_client.list_services(
            binary='nova-compute')['services']
        return [service['host'] for service in services]

    @contextlib.contextmanager
    def config_all_computes(self, *options):
        computes = self.list_compute_hosts()
        svc_mgrs = [clients.NovaServiceManager(compute, 'nova-compute',
                                               self.os_admin.services_client)
                    for compute in computes]
        ctxt_mgrs = [mgr.config_options(*options) for mgr in svc_mgrs]
        with contextlib.ExitStack() as stack:
            yield [stack.enter_context(mgr) for mgr in ctxt_mgrs]

    def get_server_xml(self, server_id):
        server = self.os_admin.servers_client.show_server(server_id)
        host = server['server']['OS-EXT-SRV-ATTR:host']
        cntrlplane_addr = whitebox_utils.get_ctlplane_address(host)
        server_instance_name = self.os_admin.servers_client.show_server(
            server_id)['server']['OS-EXT-SRV-ATTR:instance_name']

        virshxml = clients.VirshXMLClient(cntrlplane_addr)
        xml = virshxml.dumpxml(server_instance_name)
        return ET.fromstring(xml)

    def get_server_blockdevice_path(self, server_id, device_name):
        host = self.get_host_for_server(server_id)
        cntrlplane_addr = whitebox_utils.get_ctlplane_address(host)
        virshxml = clients.VirshXMLClient(cntrlplane_addr)
        blklist = virshxml.domblklist(server_id).splitlines()
        source = None
        for line in blklist:
            if device_name in line:
                target, source = line.split()
        return source

    def live_migrate(self, clients, server_id, state, target_host=None):
        """Live migrate a server.

        :param client: Clients to use when waiting for the server to
        reach the specified state.
        :param server_id: The UUID of the server to live migrate.
        :param state: Wait for the server to reach this state after live
        migration.
        :param target_host: Optional target host for the live migration.
        """
        orig_host = self.get_host_for_server(server_id)
        self.admin_servers_client.live_migrate_server(server_id,
                                                      block_migration='auto',
                                                      host=target_host)
        waiters.wait_for_server_status(clients.servers_client, server_id,
                                       state)
        if target_host:
            self.assertEqual(
                target_host, self.get_host_for_server(server_id),
                'Live migration failed, instance %s is not '
                'on target host %s' % (server_id, target_host))
        else:
            self.assertNotEqual(
                orig_host, self.get_host_for_server(server_id),
                'Live migration failed, '
                'instance %s has not changed hosts' % server_id)

    # TODO(lyarwood): Refactor all of this into a common module between
    # tempest.api.{compute,volume} and tempest.scenario.manager where this
    # has been copied from to avoid mixing api and scenario classes.
    def cleanup_volume_type(self, volume_type):
        """Clean up a given volume type.

        Ensuring all volumes associated to a type are first removed before
        attempting to remove the type itself. This includes any image volume
        cache volumes stored in a separate tenant to the original volumes
        created from the type.
        """
        volumes = self.os_admin.volumes_client_latest.list_volumes(
            detail=True, params={'all_tenants': 1})['volumes']
        type_name = volume_type['name']
        for volume in [v for v in volumes if v['volume_type'] == type_name]:
            # Use the same project client to delete the volume as was used to
            # create it and any associated secrets
            test_utils.call_and_ignore_notfound_exc(
                self.volumes_client.delete_volume, volume['id'])
            self.volumes_client.wait_for_resource_deletion(volume['id'])
        self.os_admin.volume_types_client_latest.delete_volume_type(
            volume_type['id'])

    def create_volume_type(self, client=None, name=None, backend_name=None,
                           **kwargs):
        """Creates volume type

        In a multiple-storage back-end configuration,
        each back end has a name (volume_backend_name).
        The name of the back end is declared as an extra-specification
        of a volume type (such as, volume_backend_name=LVM).
        When a volume is created, the scheduler chooses an
        appropriate back end to handle the request, according
        to the volume type specified by the user.
        The scheduler uses volume types to explicitly create volumes on
        specific back ends.

        Before using volume type, a volume type has to be declared
        to Block Storage. In addition to that, an extra-specification
        has to be created to link the volume type to a back end name.
        """

        if not client:
            client = self.os_admin.volume_types_client_latest
        if not name:
            class_name = self.__class__.__name__
            name = data_utils.rand_name(class_name + '-volume-type')
        randomized_name = data_utils.rand_name('scenario-type-' + name)

        LOG.debug("Creating a volume type: %s on backend %s",
                  randomized_name, backend_name)
        extra_specs = kwargs.pop("extra_specs", {})
        if backend_name:
            extra_specs.update({"volume_backend_name": backend_name})

        volume_type_resp = client.create_volume_type(
            name=randomized_name, extra_specs=extra_specs, **kwargs)
        volume_type = volume_type_resp['volume_type']

        self.assertIn('id', volume_type)
        self.addCleanup(self.cleanup_volume_type, volume_type)
        return volume_type

    def create_encryption_type(self, client=None, type_id=None, provider=None,
                               key_size=None, cipher=None,
                               control_location=None):
        """Creates an encryption type for volume"""
        if not client:
            client = self.os_admin.encryption_types_client_latest
        if not type_id:
            volume_type = self.create_volume_type()
            type_id = volume_type['id']
        LOG.debug("Creating an encryption type for volume type: %s", type_id)
        client.create_encryption_type(
            type_id, provider=provider, key_size=key_size, cipher=cipher,
            control_location=control_location)

    def create_encrypted_volume(self, encryption_provider, volume_type,
                                key_size=256, cipher='aes-xts-plain64',
                                control_location='front-end'):
        """Creates an encrypted volume"""
        volume_type = self.create_volume_type(name=volume_type)
        self.create_encryption_type(type_id=volume_type['id'],
                                    provider=encryption_provider,
                                    key_size=key_size,
                                    cipher=cipher,
                                    control_location=control_location)
        return self.create_volume(volume_type=volume_type['name'])
