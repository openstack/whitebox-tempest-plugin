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
from tempest import config
from tempest import test

from rhostest_tempest_plugin.services.clients import MySQLClient
from rhostest_tempest_plugin.services.clients import SSHClient
from rhostest_tempest_plugin.tests.api import base


CONF = config.CONF


class SampleRHOSTest(base.BaseRHOSTest):
    """Sample tests for documentation purposes.

    These simple tests are presented as reference on how to use
    the libs provided by this plugin.
    """

    @classmethod
    def setup_clients(cls):
        super(SampleRHOSTest, cls).setup_clients()
        cls.client = cls.servers_client
        cls.dbclient = MySQLClient()

    def tearDown(self):
        self.clear_servers()
        super(SampleRHOSTest, self).tearDown()

    @test.attr(type="smoke")
    def test_hello_world(self):
        self.assertEqual('Hello world!', 'Hello world!')

    @classmethod
    def resource_cleanup(cls):
        super(SampleRHOSTest, cls).resource_cleanup()

    @test.attr(type="smoke")
    def test_neutron_is_enabled(self):
        # This shows how to access tempest CONF variables
        self.assertTrue(CONF.service_available.neutron)

    def test_create_server_with_admin_password(self):
        # This test shows how to use the tempest clients
        server = self.create_test_server(adminPass='testpassword')
        self.assertEqual('testpassword', server['adminPass'])

    def test_ssh_client(self):
        """Connect to the db hostname and execute `uname -a`"""
        host = CONF.whitebox_plugin.nova_db_hostname
        ssh_client = SSHClient()
        command = "uname -a"
        output = ssh_client.execute(host, command)
        self.assertGreater(len(output), 0)

    def test_mysql_client(self):
        output = self.dbclient.execute_command("show tables;")
        self.assertGreater(len(output), 0)
