# Copyright 2025 Red Hat
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
#

from tempest import config
from tempest.lib.common.utils import data_utils

from whitebox_tempest_plugin.api.compute import base

CONF = config.CONF


class TestFlavorMetadata(base.BaseWhiteboxComputeTest):

    def test_flavor_metadata_is_present(self):
        "Verify flavor metadata is present in guest XML"

        xmlns = {'nova': 'http://openstack.org/xmlns/libvirt/nova/1.1'}
        msg_template = "The expected flavor metadata {} {} was not found " \
                       "and instead found {}"
        name = data_utils.rand_name(
            prefix=CONF.resource_name_prefix,
            name=self.__class__.__name__ + "-flavor")
        extra_specs = {'hw:cpu_policy': 'shared'}
        parameters_to_validate = {
            'vcpus': 2,
            'disk': 1,
            'memory': CONF.whitebox.flavor_ram_size,
            'ephemeral': 0,
            'swap': 0
        }

        flavor = self.create_flavor(
            name=name,
            vcpus=parameters_to_validate.get('vcpus'),
            ram=parameters_to_validate.get('memory'),
            disk=parameters_to_validate.get('disk'),
            extra_specs=extra_specs)

        server = self.create_test_server(flavor=flavor['id'],
                                         wait_until='ACTIVE')
        domain = self.get_server_xml(server['id'])
        metadata = domain.find('./metadata')
        flavor_element = metadata.find('.//nova:instance/nova:flavor', xmlns)

        # Confirm flavor name and id are present in metadata
        flv_metadata_name = flavor_element.attrib.get('name')
        self.assertEqual(
            name, flv_metadata_name,
            msg_template.format('name', name, flv_metadata_name))
        flv_metadata_id = flavor_element.attrib.get('id')
        self.assertEqual(
            flavor['id'], flv_metadata_id,
            msg_template.format('id', flavor['id'], flv_metadata_id))

        # Iterate and validate core flavor parameters are present in metadata
        for param, expected_val in parameters_to_validate.items():
            found_element = \
                flavor_element.find('.//nova:{}'.format(param), xmlns)
            element_value = int(found_element.text)
            self.assertEqual(
                expected_val, element_value,
                msg_template.format(param, expected_val, element_value))

        # Verify extra specs are present and correct
        extra_specs_elem = flavor_element.find('.//nova:extraSpecs', xmlns)
        extra_spec = extra_specs_elem.find('.//nova:extraSpec', xmlns)
        flv_metadata_es_name = extra_spec.get('name')
        self.assertEqual(
            'hw:cpu_policy', flv_metadata_es_name,
            msg_template.format('extra specs name', 'hw:cpu_policy',
                                flv_metadata_es_name))
        flv_metadata_es_value = extra_spec.text
        self.assertEqual(
            'shared', flv_metadata_es_value,
            msg_template.format('extra specs value', 'shared',
                                flv_metadata_es_value))
