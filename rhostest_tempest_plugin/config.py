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

compute_private_group = cfg.OptGroup(name="compute_private_config",
                                     title="Compute private config options")

ComputePrivateGroup = [
    cfg.StrOpt("target_controller",
               help="Address of a controller node."),
    cfg.StrOpt("target_ssh_user",
               help="Username of the ssh connection."),
    cfg.StrOpt("target_private_key_path",
               help="Path to the private key."),
]
