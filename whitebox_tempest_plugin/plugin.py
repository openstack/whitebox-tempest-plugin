# Copyright 2015
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


import os

from tempest import config
from tempest.test_discover import plugins

from whitebox_tempest_plugin import config as whitebox_config


class WhiteboxTempestPlugin(plugins.TempestPlugin):

    def load_tests(self):
        base_path = os.path.split(os.path.dirname(
            os.path.abspath(__file__)))[0]
        test_dir = 'whitebox_tempest_plugin/api'
        full_test_dir = os.path.join(base_path, test_dir)
        return full_test_dir, base_path

    def register_opts(self, conf):
        config.register_opt_group(conf, whitebox_config.general_group,
                                  whitebox_config.general_opts)
        config.register_opt_group(conf, whitebox_config.nova_compute_group,
                                  whitebox_config.nova_compute_opts)
        config.register_opt_group(conf, whitebox_config.database_group,
                                  whitebox_config.database_opts)
        config.register_opt_group(conf, whitebox_config.hardware_group,
                                  whitebox_config.hardware_opts)
        config.register_opt_group(conf, config.compute_features_group,
                                  whitebox_config.compute_features_group_opts)

    def get_opt_lists(self):
        return [(whitebox_config.general_group.name,
                 whitebox_config.general_opts),
                (whitebox_config.nova_compute_group.name,
                 whitebox_config.nova_compute_opts),
                (whitebox_config.database_group.name,
                 whitebox_config.database_opts),
                (whitebox_config.hardware_group.name,
                 whitebox_config.hardware_opts)]
