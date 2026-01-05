#    Copyright 2026 Red Hat
#    All Rights Reserved.
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
from tempest.exceptions import BuildErrorException
from whitebox_tempest_plugin.api.compute import base
from whitebox_tempest_plugin.common import waiters
from whitebox_tempest_plugin.services import clients
import yaml

CONF = config.CONF


class TestProviderYamlViaTraits(base.BaseWhiteboxComputeTest):
    """Validate if instance got created on same host for which
        trait is mentioned in provider.yaml
    1 - create provider.yaml template with trait
    2 - save provider.yaml in /etc/nova/provider_config/provider.yaml of
        target host
    3 - restart compute host
    4 - create a flavor with same trait with value "required"
    5 - spawn an instance
    6 - verify if instance is created in target host or not
    """

    placement_min_microversion = "1.29"

    @classmethod
    def skip_checks(cls):
        super(TestProviderYamlViaTraits, cls).skip_checks()
        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException('Need at least 2 compute nodes.')

    def setUp(self):
        super(TestProviderYamlViaTraits, self).setUp()
        self.rp_admin_cl = self.os_admin.resource_providers_client
        rps = self.rp_admin_cl.list_resource_providers()['resource_providers']
        self.host1, self.host1_id = rps[0]['name'], rps[0]['uuid']
        self.host2, self.host2_id = rps[1]['name'], rps[1]['uuid']
        # /etc/nova/provider_config/provider.yaml config location is
        # configurable for different deployments
        self.provider_config_location = CONF.whitebox.provider_config_location

        # Trait names for testing provider.yaml functionality
        # These are just identifiers - the actual host assignment
        # happens in the test methods
        self.trait_a = "CUSTOM_WB_TRAIT_A"
        self.trait_b = "CUSTOM_WB_TRAIT_B"
        self.invalid_trait = "CUSTOM_WB_TRAIT_INVALID"

    def traits_list(self):
        return self.os_admin.placement_client.list_traits()['traits']

    def assert_trait_present_in_rp(self, trait, provider):
        """Verify if created trait is added in resource provider or not.
        """
        self.assertIn(trait, self.traits_list(), "trait was not created")
        waiters.wait_for_trait_add_in_rp(self.rp_admin_cl, trait, provider)

    def _verify_trait_in_xml(self, server_id, trait):
        """Verify trait is present in guest XML metadata nova:extraSpecs.

        :param server_id: UUID of the server to check
        :param trait: Trait name to verify (e.g., 'CUSTOM_WB_TRAIT_A')
        """
        xmlns = {'nova': 'http://openstack.org/xmlns/libvirt/nova/1.1'}
        domain = self.get_server_xml(server_id)

        metadata = domain.find('./metadata')
        flavor_element = metadata.find('.//nova:instance/nova:flavor', xmlns)
        extra_specs_elem = flavor_element.find('.//nova:extraSpecs', xmlns)

        # Nova may store trait extraSpecs with or without space after colon
        trait_spec_with_space = f"trait: {trait}"
        trait_spec_no_space = f"trait:{trait}"  # noqa: E231,E262

        for extra_spec in extra_specs_elem.findall('.//nova:extraSpec', xmlns):
            spec_name = extra_spec.get('name')
            if spec_name in (trait_spec_with_space, trait_spec_no_space):
                self.assertEqual(
                    extra_spec.text, 'required',
                    f"Trait {trait} value is '{extra_spec.text}', "
                    f"expected 'required'")
                return

        self.fail(
            f"Trait {trait} not found in guest XML metadata")  # noqa: E713

    def _restart_nova_compute_service(self, host_name):
        host = clients.NovaServiceManager(
            host_name, 'nova-compute', self.os_admin.services_client)
        host.restart()

    def _create_provider_yaml_at_target_host(self, trait, target_host):
        """Creates a new trait and place the provider.yaml
        at target host then restart nova-compute service
        """
        try:
            self.os_admin.placement_client.create_trait(name=trait)
        except Exception:
            # Trait may already exist, which is fine
            pass
        template = """
            meta:
                # '1.0' is only supported version
                # as per compute.provider_config.SUPPORTED_SCHEMAS
                schema_version: "1.0"
            providers:
                # List of dicts
                - identification:
                    uuid: \\$COMPUTE_NODE
                  traits:
                    additional:
                    # trait name has to be start with CUSTOM_
                    - CUSTOM_trait_placeholder"""
        template = template.replace("CUSTOM_trait_placeholder", trait)
        template = yaml.dump(yaml.safe_load(template))
        ssh_client = clients.SSHClient(target_host)
        cmd = f"mkdir -p {self.provider_config_location}"
        ssh_client.execute(cmd, sudo=True)
        # create temp file to move with sudo to avoid permission
        # issues with redirection
        temp_file = "/tmp/provider.yaml"
        cmd = f'echo "{template}" > {temp_file}'
        ssh_client.execute(cmd)
        # Move temp file to final location with sudo
        cmd = f"mv {temp_file} {self.provider_config_location}/provider.yaml"
        ssh_client.execute(cmd, sudo=True)

    def test_valid_trait_with_provider_yaml(self):
        # First part: assign trait_a to host2 and verify VMs land there
        self._create_provider_yaml_at_target_host(self.trait_a, self.host2)
        self._restart_nova_compute_service(self.host2)
        self.assert_trait_present_in_rp(self.trait_a, self.host2_id)

        flavor_a = self.create_flavor(
            extra_specs={f"trait: {self.trait_a}": "required"})
        server1 = self.create_test_server(
            flavor=flavor_a['id'], wait_until="ACTIVE")
        self.assertEqual(self.get_host_for_server(server1['id']), self.host2)
        # Verify trait is present in guest XML metadata
        self._verify_trait_in_xml(server1['id'], self.trait_a)
        # create second guest for same trait,
        # and it should be spawned in same host
        server2 = self.create_test_server(
            flavor=flavor_a['id'], wait_until="ACTIVE")
        self.assertEqual(self.get_host_for_server(server2['id']), self.host2)

        # Second part: assign trait_b to host1 and verify VMs land there
        self._create_provider_yaml_at_target_host(self.trait_b, self.host1)
        self._restart_nova_compute_service(self.host1)
        self.assert_trait_present_in_rp(self.trait_b, self.host1_id)

        flavor_b = self.create_flavor(
            extra_specs={f"trait: {self.trait_b}": "required"})
        server3 = self.create_test_server(
            flavor=flavor_b['id'], wait_until="ACTIVE")
        self.assertNotEqual(
            self.get_host_for_server(server3['id']), self.host2)
        self.assertEqual(self.get_host_for_server(server3['id']), self.host1)
        # Verify trait is present in guest XML metadata
        self._verify_trait_in_xml(server3['id'], self.trait_b)

    def test_invalid_trait(self):
        # Test that server creation fails when trait is required but
        # no host has it (provider.yaml not created for this trait)
        self.assertNotIn(
            self.invalid_trait, self.traits_list(), "trait exists")
        flavor = self.create_flavor(
            extra_specs={f"trait: {self.invalid_trait}": "required"})

        # server creation will raise NoValidHostFound
        # because there are no host for required trait
        self.assertRaises(BuildErrorException,
                          self.create_test_server,
                          flavor=flavor['id'],
                          wait_until='ACTIVE')
