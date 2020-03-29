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

import testtools

from oslo_log import log as logging
from tempest import config

from whitebox_tempest_plugin.api.compute import base


CONF = config.CONF
LOG = logging.getLogger(__name__)


class VirtioSCSIDisk(base.BaseWhiteboxComputeTest):
    # NOTE: The class variable disk_to_create is specifically set to seven in
    # order to validate Nova bug 1686116 beyond six disks, minimum number of
    # disks present on a VM should be greater than six for tests to function
    # appropriately
    disks_to_create = 7

    @classmethod
    def setup_clients(cls):
        super(VirtioSCSIDisk, cls).setup_clients()
        cls.admin_scheduler_stats_client = \
            cls.os_admin.volume_scheduler_stats_client_latest

    def setUp(self):
        super(VirtioSCSIDisk, self).setUp()
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

    def get_created_vol_ids(self):
        """Get the ids of every volume created for the test

        :return vol_ids: a list of str's comprised of all volume id's that are
        currently tracked by the volumes client
        """
        vol_ids = [vol['id'] for vol in
                   self.volumes_client.list_volumes()['volumes']]
        return vol_ids

    def get_all_serial_ids(self, disks):
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

    @testtools.skipUnless(CONF.whitebox.available_cinder_storage > 8,
                          'Need at least 8GB of storage to execute')
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
            else:
                boot_dict['source_type'] = 'blank'
            boot_dict.update({'destination_type': 'volume',
                              'volume_size': 1,
                              'boot_index': i,
                              'disk_bus': 'scsi',
                              'delete_on_termination': True})
            bdms.append(boot_dict)

        # Provide an image_id of '' so we don't use the default
        # compute image ref here and force n-api to fetch the
        # image_meta from the BDMs.
        server = self.create_test_server(flavor=self.flavor['id'],
                                         block_device_mapping_v2=bdms,
                                         image_id='')

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

        vol_ids = self.get_created_vol_ids()
        serial_ids = self.get_all_serial_ids(scsi_disks)
        self.assertItemsEqual(vol_ids,
                              serial_ids,
                              "Created vol ids do not align with serial ids "
                              "found on the domain")

    @testtools.skipUnless(CONF.whitebox.available_cinder_storage > 8,
                          'Need at least 9GB of storage to execute')
    def test_attach_multiple_scsi_disks(self):
        """After booting an instance from an image with virtio-scsi properties
        attach multiple additional virtio-scsi disks to the point that the
        instance has more than six disks attached to a single controller.
        Validate that all volumes attach correctly to the instance.
        """
        server = self.create_test_server(flavor=self.flavor['id'],
                                         image_id=self.img_id)
        vol_ids = []
        # A virtio-scsi disk has already been attached to the server's disk
        # controller since hw_scsi_model of the image was already set to
        # 'virtio-scsi' in self.setUp(). Decrementing disks_to_create by 1.
        for _ in range(self.disks_to_create - 1):
            volume = self.create_volume()
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

        serial_ids = self.get_all_serial_ids(scsi_disks)
        self.assertItemsEqual(vol_ids,
                              serial_ids,
                              "Created vol ids do not align with serial ids "
                              "found on the domain")
