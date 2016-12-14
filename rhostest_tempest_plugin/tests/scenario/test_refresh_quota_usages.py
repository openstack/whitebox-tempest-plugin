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
from rhostest_tempest_plugin.services.mysql import default_client as dbclient
from tempest.common.utils import data_utils
from tempest import config
from tempest.lib.common import ssh
from tempest import test

CONF = config.CONF
LOG = logging.getLogger(__name__)


class RefreshQuotaUsages(base.BaseRHOSTest):

    @classmethod
    def setup_clients(cls):
        super(RefreshQuotaUsages, cls).setup_clients()
        cls.servers_client = cls.os_adm.servers_client
        cls.flvclient = cls.os_adm.flavors_client

    @classmethod
    def resource_setup(cls):
        super(RefreshQuotaUsages, cls).resource_setup()

    def _execute_ssh(self, host, ssh_user, ssh_key, command):
        ssh_client = ssh.Client(host, ssh_user, key_filename=ssh_key)
        output = ssh_client.exec_command(command)
        return output

    def _compare_resource_count(self, source1, source2):
        for quota in source1.split("\n"):
            if quota not in source2:
                return False
        return True

    def _verify_refresh_quota_usages(self, server_id):
        # Retrieve user-id and project-id for instances created
        dbcommand = """
        SELECT user_id,project_id
        FROM instances
        WHERE uuid = "{}"
        """.format(server_id)
        data = dbclient.execute_command(dbcommand)

        # Parsing the output of the mysql cli. Not pretty.
        user_id, project_id = data.split('\n')[1].split("\t")

        # Retrieve the resource count from quota usages table
        dbcommand_select = """
        SELECT resource,in_use
        FROM quota_usages
        WHERE project_id = "{}"
        """.format(project_id)
        data_orig = dbclient.execute_command(dbcommand_select)
        # Update quota usage table to fake values to mimic out of
        # sync scenario
        dbcommand_update = """
        UPDATE quota_usages
        SET in_use=99
        WHERE project_id = "{}"
        """.format(project_id)
        data = dbclient.execute_command(dbcommand_update)
        data_fake = dbclient.execute_command(dbcommand_select)
        # Verify that update work and quota usage table is different
        # from original state
        compare = self._compare_resource_count(data_orig, data_fake)
        if compare:
            return False
        # Trigger quota refresh using nova-manage command.
        # TODO(jhakimra) make a nova-manage client
        cmd = ('sudo nova-manage project quota_usage_refresh '
               '--project %s --user %s' % (project_id, user_id))
        ssh_controller = CONF.whitebox_plugin.target_controller
        ssh_username = CONF.whitebox_plugin.ssh_user
        ssh_key = CONF.whitebox_plugin.private_key_path
        self._execute_ssh(ssh_controller, ssh_username, ssh_key, cmd)
        # Retrieve resource usage count from quota usage table
        data_synced = dbclient.execute_command(dbcommand_select)
        # Verify that resource usage is in sync now
        compare = self._compare_resource_count(data_orig, data_synced)
        if not compare:
            LOG.error('Error in refreshing nova quota_usages')
            return False
        return True

    @test.services('compute')
    def test_refresh_quota_usages(self):
        flavor_name = data_utils.rand_name("test_flavor_")
        flavor_id = data_utils.rand_int_id(start=1000)
        # TODO(jhakimra): these values should be available for configuration
        # from CONF.
        self._create_nova_flavor(name=flavor_name, ram=512, vcpus=2, disk=5,
                                 fid=flavor_id)
        for _ in range(2):
            server = self._create_nova_instance(flavor_id)
        result = self._verify_refresh_quota_usages(server)
        self.assertTrue(result)
