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
from tempest import test

from tempest.api.compute import base
from tempest import config


CONF = config.CONF


class SampleTest(base.BaseV2ComputeTest):

    @test.attr(type="smoke")
    def test_neutron_is_enabled(self):
        # This shows how to access tempest CONF variables
        self.assertTrue(CONF.service_available.neutron)

    def test_create_server_with_admin_password(self):
        # This test shows how to use the tempest clients
        server = self.create_test_server(adminPass='testpassword')
        self.assertEqual('testpassword', server['adminPass'])
