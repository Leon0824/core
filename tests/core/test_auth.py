import datetime
import time

from config import application, auth
from config.database import Model
from masonite.app import App
from masonite.auth import Auth, MustVerifyEmail, Sign
from masonite.managers import AuthManager
from masonite.drivers import AuthCookieDriver, AuthJwtDriver
from masonite.helpers import password as bcrypt_password
from masonite.routes import Get
from masonite.request import Request
from masonite.snippets.auth.controllers.ConfirmController import \
    ConfirmController
from masonite.testing import TestCase
from masonite.testsuite.TestSuite import generate_wsgi
from masonite.view import View


class User(Model, MustVerifyEmail):
    __guarded__ = []


class TestAuth(TestCase):

    """Start and rollback transactions for this test
    """
    transactions = True

    def setUp(self):
        super().setUp()
        self.container = App()
        self.app = self.container
        self.app.bind('Container', self.app)
        view = View(self.container)
        self.request = Request(generate_wsgi())
        self.request.key(application.KEY)
        self.app.bind('Request', self.request)
        # self.auth = Auth(self.request, MockUser())
        self.container.bind('View', view.render)
        self.container.bind('ViewClass', view)
        self.app.bind('Application', application)
        self.app.bind('Auth', Auth)
        self.app.bind('AuthConfig', auth)
        self.app.bind('AuthManager', AuthManager)
        self.app.bind('AuthCookieDriver', AuthCookieDriver)
        self.app.bind('AuthJwtDriver', AuthJwtDriver)

        self.auth = self.app.make('Auth', User)
        self.request.load_app(self.app)

    def setUpFactories(self):
        User.create({
            'name': 'testuser123',
            'email': 'user@email.com',
            'password': bcrypt_password('secret'),
            'second_password': bcrypt_password('pass123'),
        })

    def test_auth(self):
        self.assertTrue(self.auth)

    def test_login_user(self):
        for driver in ('cookie', 'jwt'):
            self.auth.driver = driver
            self.assertTrue(self.auth.login('user@email.com', 'secret'))
            self.assertTrue(self.request.get_cookie('token'))
            self.assertEqual(self.auth.user().name, 'testuser123')

    def test_login_with_no_password(self):
        with self.assertRaises(TypeError):
            for driver in ('cookie', 'jwt'):
                self.auth.driver = driver
                self.assertTrue(self.auth.login('nopassword@email.com', None))

    # def test_can_login_with_second_password(self):
    #     self.auth.auth_model.__password__ = 'second_password'
    #     self.assertTrue(self.auth.login('user@email.com', 'pass123'))
    #     self.assertTrue(self.request.get_cookie('token'))

    def test_login_user_with_list_auth_column(self):
        for driver in ('cookie', 'jwt'):
            self.auth.driver = driver
            self.auth.auth_model.__auth__ = ['name', 'email']
            self.assertTrue(self.auth.login('testuser123', 'secret'))
            self.assertTrue(self.request.get_cookie('token'))

    def test_can_register(self):
        self.auth.register({
            'name': 'Joe',
            'email': 'joe@email.com',
            'password': 'secret'
        })

        for driver in ('cookie', 'jwt'):
            self.auth.driver = driver
            self.assertTrue(User.where('email', 'joe@email.com').first())
            self.assertNotEqual(User.where('email', 'joe@email.com').first().password, 'secret')

    def test_get_user(self):
        for driver in ('cookie', 'jwt'):
            self.auth.driver = driver
            self.assertTrue(self.auth.login_by_id(1))

    def test_get_user_returns_false_if_not_loggedin(self):
        for driver in ('cookie', 'jwt'):
            self.auth.driver = driver
            self.auth.login('user@email.com', 'wrong_secret')
            self.assertFalse(self.auth.user())

    def test_logout_user(self):
        for driver in ('cookie', 'jwt'):
            self.auth.driver = driver
            self.auth.login('user@email.com', 'secret')
            self.assertTrue(self.request.get_cookie('token'))
            self.assertTrue(self.auth.user())

            self.auth.logout()
            self.assertFalse(self.request.get_cookie('token'))
            self.assertFalse(self.auth.user())

    def test_login_user_fails(self):
        for driver in ('cookie', 'jwt'):
            self.auth.driver = driver
            self.assertFalse(self.auth.login('user@email.com', 'bad_password'))

    def test_login_user_success(self):
        for driver in ('cookie', 'jwt'):
            self.auth.driver = driver
            self.assertTrue(self.auth.login('user@email.com', 'secret'))

    def test_login_by_id(self):
        for driver in ('cookie', 'jwt'):
            self.auth.driver = driver
            self.assertTrue(self.auth.login_by_id(1))
            self.assertTrue(self.request.get_cookie('token'))
            self.assertFalse(self.auth.login_by_id(3))

    def test_login_once_does_not_set_cookie(self):
        for driver in ('cookie', 'jwt'):
            self.auth.driver = driver
            self.assertTrue(self.auth.once().login_by_id(1))
            self.assertIsNone(self.request.get_cookie('token'))

    # def test_user_is_mustverify_instance(self):
    #     self.assertIsInstance(self.auth.once().login_by_id(1), MustVerifyEmail)
    #     self.assertNotIsInstance(self.auth.once().login_by_id(1), MustVerifyEmail)

    def test_confirm_controller_success(self):
        for driver in ('jwt', 'cookie'):
            self.auth.driver = driver
            params = {'id': Sign().sign('{0}::{1}'.format(1, time.time()))}
            self.request.set_params(params)
            user = self.auth.once().login_by_id(1)
            self.request.set_user(user)

            self.app.bind('Request', self.request)
            self.app.make('Request').load_app(self.app)

            # Create the route
            route = Get('/email/verify/@id', ConfirmController.confirm_email)

            ConfirmController.get_user = User

            # Resolve the controller constructor
            controller = self.app.resolve(route.controller)

            # Resolve the method
            response = self.app.resolve(getattr(controller, route.controller_method))

            self.assertEqual(response.rendered_template, 'confirm')
            self.refreshDatabase()

    def test_confirm_controller_failure(self):
        for driver in ('cookie', 'jwt'):
            self.auth.driver = driver
            timestamp_plus_11 = datetime.datetime.now() - datetime.timedelta(minutes=11)

            params = {'id': Sign().sign('{0}::{1}'.format(1, timestamp_plus_11.timestamp()))}
            self.request.set_params(params)
            user = self.auth.once().login_by_id(1)
            self.request.set_user(user)

            self.app.bind('Request', self.request)
            self.app.make('Request').load_app(self.app)

            # Create the route
            route = Get('/email/verify/@id', ConfirmController.confirm_email)

            ConfirmController.get_user = User

            # Resolve the controller constructor
            controller = self.app.resolve(route.controller)

            # Resolve the method
            response = self.app.resolve(getattr(controller, route.controller_method))

            self.assertEqual(response.rendered_template, 'error')
