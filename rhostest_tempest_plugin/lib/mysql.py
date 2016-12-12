# Copyright 2016
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
from tempest.lib.common import ssh


CONF = config.CONF


class MySQLClient(object):
    """A client that executes MySQL commands over SSH.

    This client allows us to query databases bound to localhost only.
    It doesn't handle large outputs well due to the limitations of
    tempest.lib.common.ssh

    """

    def __init__(self, dbconf=CONF):
        self.username = dbconf.whitebox_plugin.nova_db_username
        self.password = dbconf.whitebox_plugin.nova_db_password
        self.host = dbconf.whitebox_plugin.nova_db_hostname
        self.database = dbconf.whitebox_plugin.nova_db_database
        self.ssh_key = dbconf.whitebox_plugin.private_key_path
        self.ssh_user = dbconf.whitebox_plugin.ssh_user

    def execute_command(self, command):
        ssh_client = ssh.Client(self.host, self.ssh_user,
                                key_filename=self.ssh_key)
        sql_cmd = "mysql -u{} -p{} -e '{}' {}".format(
            self.username,
            self.password,
            command,
            self.database)
        return ssh_client.exec_command(sql_cmd)

default_client = MySQLClient()
