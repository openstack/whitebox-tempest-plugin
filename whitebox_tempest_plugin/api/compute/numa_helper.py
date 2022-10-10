# Copyright 2021 Red Hat
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

from whitebox_tempest_plugin import hardware


class NUMAHelperMixin(object):
    """Mixin class containing helpers to obtain NUMA-related information about
    a server from its XML.
    """

    def get_pinning_as_set(self, server_id):
        pinset = set()
        root = self.get_server_xml(server_id)
        vcpupins = root.findall('./cputune/vcpupin')
        for pin in vcpupins:
            pinset |= hardware.parse_cpu_spec(pin.get('cpuset'))
        return pinset

    def get_server_emulator_threads(self, server_id):
        """Get the host CPU numbers to which the server's emulator threads are
        pinned.

        :param server_id: The instance UUID to look up.
        :return emulator_threads: A set of host CPU numbers.
        """
        root = self.get_server_xml(server_id)

        emulatorpins = root.findall('./cputune/emulatorpin')
        emulator_threads = set()
        for pin in emulatorpins:
            emulator_threads |= hardware.parse_cpu_spec(
                pin.get('cpuset'))

        return emulator_threads

    def get_host_pcpus_for_guest_vcpu(self, server_id, instance_cpu_ids):
        """Search the xml vcpu element of the provided instance for its cpuset.
        Convert cpuset found into a set of integers.
        """
        root = self.get_server_xml(server_id)
        vcpus = [root.find("./cputune/vcpupin[@vcpu='%s']" % cpu_id) for
                 cpu_id in instance_cpu_ids]
        cpusets = [vcpu.attrib.get('cpuset') for vcpu in vcpus]
        return hardware.parse_cpu_spec(','.join(cpusets))
