# Copyright 2020 Red Hat
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

from whitebox_tempest_plugin.tests import base
from whitebox_tempest_plugin import utils


class UtilsTestCase(base.WhiteboxPluginTestCase):

    def test_normalize_json(self):
        json = {'2': [2, 3, 1],
                '1': True,
                '4': {'b': [2, 1],
                      'a': [3, 0]},
                '3': ['b', 'a', 'z']}
        self.assertEqual({'1': True,
                          '2': [1, 2, 3],
                          '3': ['a', 'b', 'z'],
                          '4': {'a': [0, 3],
                                'b': [1, 2]}},
                         utils.normalize_json(json))
