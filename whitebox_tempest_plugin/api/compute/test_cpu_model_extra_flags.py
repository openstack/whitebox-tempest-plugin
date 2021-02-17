# Copyright 2018 Red Hat
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


class CpuModelExtraFlagsTest(base.BaseWhiteboxComputeTest):

    @testtools.skipUnless(CONF.whitebox.cpu_model, "'cpu_model' must be set")
    @testtools.skipUnless(CONF.whitebox.cpu_model_extra_flags,
                          "'cpu_model_extra_flags must be set")
    def test_cpu_model_extra_flags(self):
        server = self.create_test_server(wait_until="ACTIVE")
        root = self.get_server_xml(server['id'])
        # Assert that the correct CPU model as well as the proper flags
        # are correctly defined in the instance XML
        self.assertEqual(
            CONF.whitebox.cpu_model,
            root.find("cpu[@mode='custom']/model").text,
            'Wrong CPU model defined in instance xml')
        for flag in CONF.whitebox.cpu_model_extra_flags:
            if flag.startswith('-'):
                self.assertNotEmpty(
                    root.findall(
                        'cpu[@mode="custom"]/'
                        'feature[@name="%s"][@policy="disable"]' %
                        flag.strip('-')),
                    "Disabled feature '%s' not found in the XML" %
                    flag.strip('-'))
            else:
                self.assertNotEmpty(
                    root.findall(
                        'cpu[@mode="custom"]/'
                        'feature[@name="%s"][@policy="require"]' %
                        flag.strip('+')),
                    "Required feature '%s' not found in the XML" %
                    flag.strip('+'))
