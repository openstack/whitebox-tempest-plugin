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
import urlparse

from tempest import config
from tempest.lib.common import ssh


CONF = config.CONF


class SSHClient(object):
    """A client to execute remote commands, based on tempest.lib.common.ssh."""

    def __init__(self):
        self.ssh_key = CONF.compute_private_config.target_private_key_path
        self.ssh_user = CONF.compute_private_config.target_ssh_user

    def execute(self, hostname=None, cmd=None):
        ssh_client = ssh.Client(hostname, self.ssh_user,
                                key_filename=self.ssh_key)
        return ssh_client.exec_command(cmd)


class VirshXMLClient(SSHClient):
    def __init__(self, hostname=None):
        super(VirshXMLClient, self).__init__()
        self.host = hostname

    def dumpxml(self, domain):
        command = "sudo virsh dumpxml {}".format(domain)
        return self.execute(self.host, command)


class MySQLClient(SSHClient):
    def __init__(self):
        super(MySQLClient, self).__init__()
        # the nova conf file may contain a private IP.
        # let's just assume the db is available on the same node.
        self.host = CONF.compute_private_config.target_controller

        # discover db connection params by accessing nova.conf remotely
        ssh_client = SSHClient()
        cmd = 'grep "connection=mysql+pymysql://nova:" /etc/nova/nova.conf'
        connection = ssh_client.execute(self.host, "sudo {}".format(cmd))
        connection_url = "=".join(connection.split("=")[1:])
        p = urlparse.urlparse(connection_url)

        self.username = p.username
        self.password = p.password
        self.database = p.path[1:]

    def execute_command(self, command):
        sql_cmd = "mysql -u{} -p{} -e '{}' {}".format(
            self.username,
            self.password,
            command,
            self.database)
        return self.execute(self.host, sql_cmd)


class NovaManageClient(SSHClient):
    def __init__(self):
        super(NovaManageClient, self).__init__()
        self.hostname = CONF.compute_private_config.target_controller

    def execute_command(self, command):
        nova_cmd = "sudo nova-manage {}".format(command)
        return self.execute(self.hostname, nova_cmd)
