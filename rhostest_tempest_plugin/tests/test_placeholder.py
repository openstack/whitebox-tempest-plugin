# Copyright 2018 Red Hat
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

from rhostest_tempest_plugin.tests import base


class PlaceholderTestCase(base.WhiteboxPluginTestCase):
    # TODO(artom) Remove this class when we add actual unit tests. This class
    # is only necessary to to avoid stestr complaining about not finding any
    # tests.

    def test_placeholder(self):
        pass
