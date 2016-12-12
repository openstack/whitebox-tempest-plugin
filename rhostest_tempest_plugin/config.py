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

from oslo_config import cfg

whitebox_plugin_group = cfg.OptGroup(name="whitebox_plugin",
                                     title="Whitebox config options")

WhiteboxPluginGroup = [
    cfg.StrOpt("nova_db_hostname",
               help="Hostname or address of the nova db host."),
    cfg.StrOpt("nova_db_username",
               help="Username for the database connection."),
    cfg.StrOpt("nova_db_password",
               help="Password for the database connection."),
    cfg.StrOpt("nova_db_database",
               help="The database name for the nova database connection."),
    cfg.StrOpt("target_controller",
               help="Address of a controller node."),
    cfg.StrOpt("ssh_user",
               help="Username of the ssh connection."),
    cfg.StrOpt("private_key_path",
               help="Path to the private key."),
]
