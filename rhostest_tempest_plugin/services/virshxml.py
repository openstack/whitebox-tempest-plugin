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


class VirshXMLClient(object):
    def __init__(self, hostname=None):
        self.hostname = hostname
        self.ssh_user = CONF.whitebox_plugin.ssh_user
        self.ssh_key = CONF.whitebox_plugin.private_key_path

    def dumpxml(self, domain):
        ssh_client = ssh.Client(self.hostname, self.ssh_user,
                                key_filename=self.ssh_key)
        command = "sudo virsh dumpxml {}".format(domain)
        return ssh_client.exec_command(command)
