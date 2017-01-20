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
#
# Parameters required in etc/tempest.conf
#    [whitebox_plugin]
#    nova_db_hostname=
#    nova_db_username=
#    nova_db_password=
#    nova_db_database=
#    target_ssh_user=
#    target_private_key_path=
#
from oslo_log import log as logging
from rhostest_tempest_plugin import base
from rhostest_tempest_plugin.services import clients
from tempest.common.utils import data_utils
from tempest import config
from tempest import test

CONF = config.CONF
LOG = logging.getLogger(__name__)


class ArchiveDeletedRowsTest(base.BaseRHOSTest):

    @classmethod
    def setup_clients(cls):
        super(ArchiveDeletedRowsTest, cls).setup_clients()
        cls.servers_client = cls.os_adm.servers_client
        cls.dbclient = clients.MySQLClient()
        cls.novamanageclient = clients.NovaManageClient()

    def _create_delete_instances(self, count):
        for _ in range(count):
            server = self._create_nova_instance(cleanup=False)
            self.servers_client.delete_server(server)

    @test.services('compute')
    def test_archive_deleted_rows(self):

        # Create/Delete 5 servers
        self._create_delete_instances(count=5)

        # `select id,uuid,deleted from nova.instances where deleted != 0;`
        dbcommand = """
        SELECT id,uuid,deleted
        FROM nova.instances
        WHERE deleted != 0
        """
        data = self.dbclient.execute_command(dbcommand)
        count = len(data.split("\n")) - 2
        self.assertGreaterEqual(count, 5)

        # archive deleted rows
        cmd = "db archive_deleted_rows 3"
        self.novamanageclient.execute_command(cmd)

        data = self.dbclient.execute_command(dbcommand)
        count = len(data.split("\n")) - 2
        self.assertEqual(count, 3)
