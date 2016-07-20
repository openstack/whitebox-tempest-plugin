from tempest import test

from tempest.api.compute import base
from tempest import config


CONF = config.CONF


class SampleTest(base.BaseV2ComputeTest):

    @test.attr(type="smoke")
    def test_success(self):
        self.assertTrue(CONF.service_available.neutron)

    def test_fail(self):
        self.assertFalse(CONF.service_available.neutron)

    def test_create_server_with_admin_password(self):
        # If an admin password is provided on server creation, the server's
        # root password should be set to that password.
        server = self.create_test_server(adminPass='testpassword')

        # Verify the password is set correctly in the response
        self.assertEqual('testpassword', server['adminPass'])
