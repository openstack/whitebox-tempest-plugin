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

# Requirements
# 1. Grant remote access rights for database
#    GRANT ALL PRIVILEGES ON *.* TO '<user>'@'%' IDENTIFIED BY '<passowrd> WITH GRANT OPTION;
#    The above user/password information is stored in tempest config

from tempest.api.compute import base
from tempest.common import tempest_fixtures as fixtures
from tempest.common.utils import data_utils
from tempest.lib.common.utils import test_utils
from tempest.lib.common import ssh
from tempest.common import waiters
from tempest import test
from tempest import config
from tempest.lib import exceptions
from oslo_log import log as logging
from rhostest_tempest_plugin.lib.mysql import default_client as dbclient
import json
import itertools


CONF = config.CONF
LOG = logging.getLogger(__name__)

class VCPUPinningTest(base.BaseV2ComputeAdminTest):

    @classmethod
    def setup_clients(cls):
        super(VCPUPinningTest, cls).setup_clients()
        cls.client = cls.os_adm.aggregates_client
        cls.flavors_client = cls.os_adm.flavors_client
        cls.hosts_client=cls.os_adm.hosts_client
        cls.servers_client=cls.os_adm.servers_client
    
    @classmethod
    def resource_setup(cls):
        super(VCPUPinningTest, cls).resource_setup()

    def _create_vcpu_pinned_flavor(self,name,ram,vcpus,disk,fid,extraspecs):
        # This function creates a flavor with provided parameters
        flavor = self.flavors_client.create_flavor(name=name,
                                           ram=ram, vcpus=vcpus,
                                           disk=disk,
                                           id=fid)['flavor']
        self.assertEqual(flavor['name'], name)
        self.assertEqual(flavor['vcpus'], vcpus)
        self.assertEqual(flavor['disk'], disk)
        self.assertEqual(flavor['ram'], ram)
        self.assertEqual(int(flavor['id']), fid)
        # SET extra specs to the flavor created in setUp
        set_body = self.flavors_client.set_flavor_extra_spec(flavor['id'],**extraspecs)['extra_specs']
        self.assertEqual(set_body, extraspecs)

        return flavor

    def _create_pinned_instance(self,flavor):
        self.name = data_utils.rand_name("instance")
        self.server = self.servers_client.create_server(
            name=self.name, imageRef=CONF.compute.image_ref, flavorRef=flavor)['server']
        server_id = self.server['id']
        waiters.wait_for_server_status(self.servers_client, server_id,'ACTIVE')
        return server_id

    def _test_cpu_threads_policy(self,policy,ram,vcpus,disk):	    
        specs = {"hw:cpu_policy": "dedicated", "aggregate_instance_extra_specs:pinned": "true",
                 "hw:cpu_thread_policy":policy}
        flavor_name_prefix = 'test_flavor_' + policy +"_"
        flavor_name = data_utils.rand_name(flavor_name_prefix)
        flavor_id = data_utils.rand_int_id(start=1000)
        self._create_vcpu_pinned_flavor(name=flavor_name,
                                        ram=ram, vcpus=vcpus,
                                        disk=disk,
                                        fid=flavor_id,
                                        extraspecs=specs)        
        server = self._create_pinned_instance(flavor_id);        
        server_cpus = []
        dbcommand = "select numa_topology from instance_extra where instance_uuid = \"" + server + "\"";
        server_cpus = self._get_cpuinfo_from_nova_db(dbcommand, 'cpu_pinning_raw')
        dbcommand = "select numa_topology from compute_nodes where hypervisor_hostname = \"" + str(dbclient.db_config['host']) + "\"";
        cpuset=self._get_cpuinfo_from_nova_db(dbcommand=dbcommand, key='cpuset')
        siblings=self._get_cpuinfo_from_nova_db(dbcommand=dbcommand, key='siblings')        
        has_SMT_arch=False
        for item in siblings:
            if item:
                has_SMT_arch=True                
        if policy == "require":
            if has_SMT_arch:
                return  bool(set(server_cpus)< set(itertools.chain.from_iterable(siblings)))                           
            else:
                LOG.error('host:%s does not have SMT architecture to exercise cpu_thread_policy:REQUIRE' % (self.dbhost))
                return False;
        elif policy == "prefer":
                return  bool(set(server_cpus)< set(cpuset))                           
        elif policy == "isolate":
            core_id=[]
            if has_SMT_arch:
                for item in server_cpus:
                    for i in range(len(siblings)):
                        if item in siblings[i]:
                            core_id.append(i)
                if(len(core_id)> len(set(core_id))):
                    return False
                else:
                    return True
        else:
            LOG.error('Unknown cpu_thread_policy:%s' % policy)
            return False;        
        return None
            
    def _get_cpuinfo_from_nova_db(self,dbcommand,key):
        #This function retrieves information such as cpus pinned
        #to instances, cpuset and sibling information for compute
        #nodes.
        conn=dbclient.connect()
        cursor=conn.cursor()
        cursor.execute(dbcommand)
        data=cursor.fetchone()
        data_json=json.loads(str(data[0]))
        cpuinfo=[]
        for i in range(len(data_json['nova_object.data']['cells'])):
            row = data_json['nova_object.data']['cells'][i]['nova_object.data'][key]
            if isinstance(row, dict):
                for key, value in row.items():
                    cpuinfo.append(value)
            else:
                cpuinfo.extend(row)
        conn.close()
        return cpuinfo
    
    def _create_aggregate_with_multiple_hosts(self):
        # This function allows to create aggregate with multiple
        # hosts attached to it. The meta data key is set to true
        # to allow filtering of this aggregate during scheduling.
        aggregate_name = data_utils.rand_name('aggregate-scenario')
        metadata = {'pinned': 'true'}
        aggregate = (self.client.create_aggregate(name=aggregate_name)['aggregate'])
        self.assertEqual(aggregate['name'], aggregate_name)
        aggregate_id=aggregate['id']
        aggregate = self.client.set_metadata(aggregate_id,metadata=metadata)
        for key, value in metadata.items():
            self.assertEqual(metadata[key],aggregate['aggregate']['metadata'][key])
        hosts = self.hosts_client.list_hosts()['hosts']
        self.assertTrue(len(hosts) >= 1)
        computes = [x for x in hosts if x['service'] == 'compute']
        self.host=computes[0]['host_name']
        for index in range(len(computes)):
            aggregate = self.client.add_host(aggregate_id,host=computes[index]['host_name'])['aggregate']
            self.assertIn(computes[index]['host_name'], aggregate['hosts'])        
        return None


    @test.services('compute')
    def test_vcpu_pinning_policies(self):
        
        
        #Verify cpu threads policy for even number of vcpus
        ram=512
        vcpus=2
        disk=5
        self._create_aggregate_with_multiple_hosts()
        policy="isolate"
        self._test_cpu_threads_policy(policy,ram=ram,vcpus=vcpus,disk=disk)
        policy="prefer"
        self._test_cpu_threads_policy(policy,ram=ram,vcpus=vcpus,disk=disk)
        policy="require"
        self._test_cpu_threads_policy(policy,ram=ram,vcpus=vcpus,disk=disk)
        #Verify cpu threads policy for odd number of vcpus
        vcpus=3
        policy="isolate"
        self._test_cpu_threads_policy(policy,ram=ram,vcpus=vcpus,disk=disk)
        policy="prefer"
        self._test_cpu_threads_policy(policy,ram=ram,vcpus=vcpus,disk=disk)
        policy="require"
        self._test_cpu_threads_policy(policy,ram=ram,vcpus=vcpus,disk=disk)

