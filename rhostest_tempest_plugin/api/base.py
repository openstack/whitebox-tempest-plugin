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
from oslo_log import log as logging

from tempest import config
from tempest import test

from tempest.common import compute
from tempest.common import waiters

from tempest.lib.common.utils import test_utils

CONF = config.CONF
LOG = logging.getLogger(__name__)


class BaseRHOSTest(test.BaseTestCase):
    """Base test case class for RHOS compute tests."""

    credentials = ['primary']

    @classmethod
    def skip_checks(cls):
        pass

    @classmethod
    def setup_clients(cls):
        super(BaseRHOSTest, cls).setup_clients()
        cls.servers_client = cls.os.servers_client
        cls.server_groups_client = cls.os.server_groups_client
        cls.flavors_client = cls.os.flavors_client
        cls.compute_images_client = cls.os.compute_images_client
        cls.extensions_client = cls.os.extensions_client
        cls.floating_ip_pools_client = cls.os.floating_ip_pools_client
        cls.floating_ips_client = cls.os.compute_floating_ips_client
        cls.keypairs_client = cls.os.keypairs_client
        cls.security_group_rules_client = (
            cls.os.compute_security_group_rules_client)
        cls.security_groups_client = cls.os.compute_security_groups_client
        cls.quotas_client = cls.os.quotas_client
        cls.quota_classes_client = cls.os.quota_classes_client
        cls.compute_networks_client = cls.os.compute_networks_client
        cls.limits_client = cls.os.limits_client
        cls.volumes_extensions_client = cls.os.volumes_extensions_client
        cls.snapshots_extensions_client = cls.os.snapshots_extensions_client
        cls.interfaces_client = cls.os.interfaces_client
        cls.fixed_ips_client = cls.os.fixed_ips_client
        cls.availability_zone_client = cls.os.availability_zone_client
        cls.agents_client = cls.os.agents_client
        cls.aggregates_client = cls.os.aggregates_client
        cls.services_client = cls.os.services_client
        cls.instance_usages_audit_log_client = (
            cls.os.instance_usages_audit_log_client)
        cls.hypervisor_client = cls.os.hypervisor_client
        cls.certificates_client = cls.os.certificates_client
        cls.migrations_client = cls.os.migrations_client
        cls.security_group_default_rules_client = (
            cls.os.security_group_default_rules_client)
        cls.versions_client = cls.os.compute_versions_client

    @classmethod
    def resource_setup(cls):
        super(BaseRHOSTest, cls).resource_setup()
        cls.build_interval = CONF.compute.build_interval
        cls.build_timeout = CONF.compute.build_timeout
        cls.image_ref = CONF.compute.image_ref
        cls.image_ref_alt = CONF.compute.image_ref_alt
        cls.flavor_ref = CONF.compute.flavor_ref
        cls.flavor_ref_alt = CONF.compute.flavor_ref_alt
        cls.ssh_user = CONF.validation.image_ssh_user
        cls.image_ssh_user = CONF.validation.image_ssh_user
        cls.image_ssh_password = CONF.validation.image_ssh_password
        cls.servers = []
        cls.images = []
        cls.security_groups = []
        cls.server_groups = []

    @classmethod
    def setup_credentials(cls):
        cls.set_network_resources()
        super(BaseRHOSTest, cls).setup_credentials()

    @classmethod
    def resource_cleanup(cls):
        cls.clear_images()
        cls.clear_servers()
        cls.clear_security_groups()
        cls.clear_server_groups()
        super(BaseRHOSTest, cls).resource_cleanup()

    @classmethod
    def clear_servers(cls):
        LOG.debug('Clearing servers: %s', ','.join(
            server['id'] for server in cls.servers))
        for server in cls.servers:
            try:
                test_utils.call_and_ignore_notfound_exc(
                    cls.servers_client.delete_server, server['id'])
            except Exception:
                LOG.exception('Deleting server %s failed' % server['id'])

        for server in cls.servers:
            try:
                waiters.wait_for_server_termination(cls.servers_client,
                                                    server['id'])
            except Exception:
                LOG.exception('Waiting for deletion of server %s failed'
                              % server['id'])

    @classmethod
    def clear_images(cls):
        LOG.debug('Clearing images: %s', ','.join(cls.images))
        for image_id in cls.images:
            try:
                test_utils.call_and_ignore_notfound_exc(
                    cls.compute_images_client.delete_image, image_id)
            except Exception:
                LOG.exception('Exception raised deleting image %s' % image_id)

    @classmethod
    def clear_security_groups(cls):
        LOG.debug('Clearing security groups: %s', ','.join(
            str(sg['id']) for sg in cls.security_groups))
        for sg in cls.security_groups:
            try:
                test_utils.call_and_ignore_notfound_exc(
                    cls.security_groups_client.delete_security_group, sg['id'])
            except Exception as exc:
                LOG.info('Exception raised deleting security group %s',
                         sg['id'])
                LOG.exception(exc)

    @classmethod
    def clear_server_groups(cls):
        LOG.debug('Clearing server groups: %s', ','.join(cls.server_groups))
        for server_group_id in cls.server_groups:
            try:
                test_utils.call_and_ignore_notfound_exc(
                    cls.server_groups_client.delete_server_group,
                    server_group_id
                )
            except Exception:
                LOG.exception('Exception raised deleting server-group %s',
                              server_group_id)

    @classmethod
    def create_test_server(cls, validatable=False, volume_backed=False,
                           **kwargs):
        """Wrapper utility that returns a test server.

        This wrapper utility calls the common create test server and
        returns a test server. The purpose of this wrapper is to minimize
        the impact on the code of the tests already using this
        function.
        :param validatable: Whether the server will be pingable or sshable.
        :param volume_backed: Whether the instance is volume backed or not.
        """
        tenant_network = cls.get_tenant_network()
        body, servers = compute.create_test_server(
            cls.os,
            validatable,
            validation_resources=cls.validation_resources,
            tenant_network=tenant_network,
            volume_backed=volume_backed,
            **kwargs)

        cls.servers.extend(servers)

        return body
