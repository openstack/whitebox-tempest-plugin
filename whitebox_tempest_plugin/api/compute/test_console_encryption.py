# Copyright 2024 Red Hat Inc.
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
from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.services.clients import SSHClient

CONF = config.CONF


class TestVencrypt(base.BaseWhiteboxComputeTest):

    @classmethod
    def skip_checks(cls):
        super(TestVencrypt, cls).skip_checks()
        if not CONF.compute_feature_enabled.vencrypt:
            raise cls.skipException("vencrypt is not enabled")

    def setUp(self):
        super(TestVencrypt, self).setUp()
        server = self.create_test_server(wait_until='ACTIVE')
        server = self.os_admin.servers_client.show_server(server["id"])[
            'server']
        self.instance = server["OS-EXT-SRV-ATTR:instance_name"]
        self.host = self.get_host_for_server(server['id'])
        self.ssh_cl = SSHClient(self.host)

    def test_via_qemu_logs(self):
        cmd = f'cat /var/log/libvirt/qemu/{self.instance}.log'
        cmd += '| grep vnc'
        data = self.ssh_cl.execute(cmd, sudo=True).splitlines()

        # qemu logs should have vnc-tls object
        # -object '{
        #       "qom-type":"tls-creds-x509",
        #       "id":"vnc-tls-creds0",
        #       "dir":"/etc/pki/qemu",
        #       "endpoint":"server",
        #       "verify-peer":true}'
        tls_objects = [
            'vnc-tls' in obj and '"verify-peer":true' in obj for obj in data
        ]
        self.assertTrue(any(tls_objects))
