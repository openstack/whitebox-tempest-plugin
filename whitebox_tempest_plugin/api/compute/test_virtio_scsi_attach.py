# Copyright 2020 Red Hat Inc.
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
from tempest.lib.exceptions import Forbidden

from whitebox_tempest_plugin.api.compute import base


CONF = config.CONF
LOG = logging.getLogger(__name__)


class VirtioSCSIBase(base.BaseWhiteboxComputeTest):

    def setUp(self):
        super(VirtioSCSIBase, self).setUp()
        # NOTE: Flavor and image are common amongst every test of the class
        # so setting them once in setUP method.
        self.flavor = self.create_flavor()
        self.img_id = self.copy_default_image(hw_scsi_model='virtio-scsi',
                                              hw_disk_bus='scsi')

    def get_attached_disks(self, server_id):
        """Returns all disk devices attached to the server

        :param server_id: the uuid of the instance as a str
        :return disks: a list of xml elements, the elements are all disks
        in the devices section of the server's xml
        """
        root = self.get_server_xml(server_id)
        disks = root.findall("./devices/disk")
        return disks

    def get_scsi_disks(self, server_id, controller_index):
        """Returns all scsi disks attached to a specific disk controller
        for the server

        :param server_id: the uuid of the instance as a str
        :controller_index: the disk controller index to search
        :return scsi_disks: a list of xml elements, the elements are all scsi
        disks managed by the provided controller_index parameter
        """
        all_disks = self.get_attached_disks(server_id)
        scsi_disks = [disk for disk in all_disks
                      if disk.find("target[@bus='scsi']") is not None and
                      disk.find("address[@controller="
                                "'%s']" % controller_index) is not None]
        return scsi_disks

    def get_scsi_disk_controllers(self, server_id):
        """Returns all scsi disk controllers for the server

        :param server_id: the uuid of the instance as a str
        :return disk_cntrls: a list of xml elements, the elements are all
        scsi disk controllers found in the devices section of the server
        xml
        """
        root = self.get_server_xml(server_id)
        disk_cntrls = root.findall("./devices/controller[@type='scsi']"
                                   "[@model='virtio-scsi']")
        return disk_cntrls

    def get_attached_volume_ids(self, server_id):
        """Get the id of every volume attached to the server

        :returns: A list of volume id's that are attached to the instance
        """
        attachments = self.servers_client.list_volume_attachments(server_id)
        return [a.get('volumeId') for a in attachments['volumeAttachments']]

    def get_attached_serial_ids(self, disks):
        """Create a list of serial ids from a list of disks

        :param disks, a list of xml elements, each element should be the xml
        representation of a disk
        return serial_ids: a list of str's comprised of every serial id found
        from the provided list of xml described disks
        """
        serial_ids = [disk.find('serial').text for disk in disks
                      if getattr(disk.find('serial'), 'text', None) is not
                      None]
        return serial_ids


class VirtioSCSIDiskMultiAttachment(VirtioSCSIBase):
    # NOTE: The class variable disk_to_create is specifically set to seven in
    # order to validate Nova bug 1686116 beyond six disks, minimum number of
    # disks present on a VM should be greater than six for tests to function
    # appropriately
    disks_to_create = 7

    @classmethod
    def skip_checks(cls):
        super(VirtioSCSIDiskMultiAttachment, cls).skip_checks()
        if getattr(CONF.whitebox, 'max_disk_devices_to_attach', None):
            if CONF.whitebox.max_disk_devices_to_attach < cls.disks_to_create:
                msg = "Tests may only run if allowed disk attachment " \
                      "is %s or more devices" % cls.disks_to_create
                raise cls.skipException(msg)
        required_disk_space = \
            CONF.whitebox.flavor_volume_size + cls.disks_to_create
        if CONF.whitebox.available_cinder_storage < required_disk_space:
            msg = "Need more than  %sGB of storage to execute" \
                % required_disk_space
            raise cls.skipException(msg)

    def test_boot_with_multiple_disks(self):
        """Using block device mapping, boot an instance with more than six
        volumes. Total volume count is determined by class variable
        disks_to_create. Server should boot correctly and should only have
        one disk controller with seven or more disks present in xml.
        """
        bdms = []
        for i in range(self.disks_to_create):
            boot_dict = {}
            if i == 0:
                boot_dict['uuid'] = self.img_id
                boot_dict['source_type'] = 'image'
                boot_dict['volume_size'] = CONF.whitebox.flavor_volume_size
            else:
                boot_dict['source_type'] = 'blank'
                boot_dict['volume_size'] = 1
            boot_dict.update({'destination_type': 'volume',
                              'boot_index': i,
                              'disk_bus': 'scsi',
                              'delete_on_termination': True})
            bdms.append(boot_dict)

        # Provide an image_id of '' so we don't use the default
        # compute image ref here and force n-api to fetch the
        # image_meta from the BDMs.
        server = self.create_test_server(flavor=self.flavor['id'],
                                         block_device_mapping_v2=bdms,
                                         image_id='',
                                         wait_until='ACTIVE')

        disk_ctrl = self.get_scsi_disk_controllers(server_id=server['id'])
        self.assertEqual(len(disk_ctrl), 1,
                         "One and only one SCSI Disk controller should have "
                         "been created but instead "
                         "found: {} controllers".format(len(disk_ctrl)))

        controller_index = disk_ctrl[0].attrib['index']
        scsi_disks = self.get_scsi_disks(server_id=server['id'],
                                         controller_index=controller_index)
        self.assertEqual(len(scsi_disks),
                         self.disks_to_create,
                         "Expected {} scsi disks on the domain but "
                         "found {}".format(self.disks_to_create,
                                           len(scsi_disks)))

        attached_volume_ids = self.get_attached_volume_ids(server['id'])
        attached_serial_ids = self.get_attached_serial_ids(scsi_disks)

        # Assert that the attached volume ids are present as serials
        self.assertCountEqual(attached_volume_ids, attached_serial_ids)

    def test_attach_multiple_scsi_disks(self):
        """After booting an instance from an image with virtio-scsi properties
        attach multiple additional virtio-scsi disks to the point that the
        instance has more than six disks attached to a single controller.
        Validate that all volumes attach correctly to the instance.
        """
        server = self.create_test_server(flavor=self.flavor['id'],
                                         image_id=self.img_id,
                                         wait_until='ACTIVE')
        vol_ids = []
        # A virtio-scsi disk has already been attached to the server's disk
        # controller since hw_scsi_model of the image was already set to
        # 'virtio-scsi' in self.setUp(). Decrementing disks_to_create by 1.
        for _ in range(self.disks_to_create - 1):
            volume = self.create_volume(size=1)
            vol_ids.append(volume['id'])
            self.addCleanup(self.delete_volume, volume['id'])
            self.attach_volume(server, volume)

        disk_ctrl = self.get_scsi_disk_controllers(server_id=server['id'])
        self.assertEqual(len(disk_ctrl), 1,
                         "One and only one SCSI Disk controller should have "
                         "been created but instead "
                         "found: {} controllers".format(len(disk_ctrl)))

        cntrl_index = disk_ctrl[0].attrib['index']
        scsi_disks = self.get_scsi_disks(server_id=server['id'],
                                         controller_index=cntrl_index)
        self.assertEqual(len(scsi_disks),
                         self.disks_to_create,
                         "Expected {} disks but only "
                         "found {}".format(self.disks_to_create,
                                           len(scsi_disks)))

        attached_volume_ids = self.get_attached_volume_ids(server['id'])
        attached_serial_ids = self.get_attached_serial_ids(scsi_disks)

        # Assert that the volumes IDs we attached are listed as attached
        self.assertCountEqual(vol_ids, attached_volume_ids)

        # Assert that the volume IDs we attached are present in the serials
        self.assertCountEqual(vol_ids, attached_serial_ids)


class VirtioSCSIDiskRestrictAttachments(VirtioSCSIBase):

    @classmethod
    def skip_checks(cls):
        super(VirtioSCSIDiskRestrictAttachments, cls).skip_checks()
        if getattr(CONF.whitebox, 'max_disk_devices_to_attach', None) is None:
            msg = "Requires max_disk_devices_to_attach to be explicitly set " \
                  "in the deployment to test"
            raise cls.skipException(msg)
        required_disk_space = CONF.whitebox.flavor_volume_size + \
            CONF.whitebox.max_disk_devices_to_attach
        if CONF.whitebox.available_cinder_storage < required_disk_space:
            msg = "Need more than  %sGB of storage to execute" \
                % required_disk_space
            raise cls.skipException(msg)

    def test_max_iscsi_disks_attachment_enforced(self):
        """After booting an instance from an image with virtio-scsi properties
        attach multiple additional virtio-scsi disks to the point that the
        instance reaches the limit of allowed attached disks. After confirming
        they are all attached correctly, add one more volume and confirm the
        action is Forbidden.
        """
        disks_to_create = CONF.whitebox.max_disk_devices_to_attach
        server = self.create_test_server(flavor=self.flavor['id'],
                                         image_id=self.img_id,
                                         wait_until='ACTIVE')
        vol_ids = []
        # A virtio-scsi disk has already been attached to the server's disk
        # controller since hw_scsi_model of the image was already set to
        # 'virtio-scsi' in self.setUp(). Decrementing disks_to_create by 1.
        for _ in range(disks_to_create - 1):
            volume = self.create_volume(size=1)
            vol_ids.append(volume['id'])
            self.addCleanup(self.delete_volume, volume['id'])
            self.attach_volume(server, volume)

        disk_ctrl = self.get_scsi_disk_controllers(server_id=server['id'])
        self.assertEqual(len(disk_ctrl), 1,
                         "One and only one SCSI Disk controller should have "
                         "been created but instead "
                         "found: {} controllers".format(len(disk_ctrl)))

        cntrl_index = disk_ctrl[0].attrib['index']
        scsi_disks = self.get_scsi_disks(server_id=server['id'],
                                         controller_index=cntrl_index)
        self.assertEqual(len(scsi_disks),
                         disks_to_create,
                         "Expected {} disks but only "
                         "found {}".format(disks_to_create,
                                           len(scsi_disks)))

        attached_volume_ids = self.get_attached_volume_ids(server['id'])
        attached_serial_ids = self.get_attached_serial_ids(scsi_disks)

        # Assert that the volumes IDs we attached are listed as attached
        self.assertCountEqual(vol_ids, attached_volume_ids)

        # Assert that the volume IDs we attached are present in the serials
        self.assertCountEqual(vol_ids, attached_serial_ids)

        # Create and attempt to attach one more volume to guest and confirm
        # action is forbidden
        volume = self.create_volume(size=1)
        self.addCleanup(self.delete_volume, volume['id'])
        self.assertRaises(Forbidden, self.attach_volume, server, volume)
