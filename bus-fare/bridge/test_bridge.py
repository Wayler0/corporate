"""python3 -m unittest test_bridge   (run inside bus-fare/bridge; needs no Uno and no server)"""
import unittest
from unittest import mock

import requests

import bridge


class FakePort:
    def __init__(self):
        self.written = []

    def write(self, data):
        self.written.append(data.decode().strip())


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.port = FakePort()
        self.bridge = bridge.Bridge(self.port, 'http://server/', log=lambda text: None)
        self.bridge.ready = True

    def with_api(self, answer):
        """Make the server give this answer (or raise it, if it is an exception)."""
        patcher = mock.patch.object(self.bridge, 'api', side_effect=answer if isinstance(answer, Exception) else None,
                                    return_value=None if isinstance(answer, Exception) else answer)
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_ready_sends_the_servers_fare(self):
        self.bridge.ready = False
        api = self.with_api({'fare': 70})
        self.bridge.on_line('READY')
        api.assert_called_once_with('GET', '/api/status/')
        self.assertTrue(self.bridge.ready)
        self.assertEqual(self.port.written, ['FARE 70'])

    def test_tap_is_answered_with_res(self):
        api = self.with_api({'result': 'PAID', 'fare': 50, 'balance': 450})
        self.bridge.on_line('TAP E5734107')
        api.assert_called_once_with('POST', '/api/tap/', {'card_uid': 'E5734107'})
        self.assertEqual(self.port.written, ['RES PAID 50 450'])

    def test_repeat_and_low_carry_fare_and_balance(self):
        self.with_api({'result': 'LOW', 'fare': 50, 'balance': 30})
        self.bridge.on_line('TAP 11223344')
        self.assertEqual(self.port.written, ['RES LOW 50 30'])

    def test_unknown_is_sent_without_a_balance(self):
        self.with_api({'result': 'UNKNOWN', 'fare': 50, 'balance': 0})
        self.bridge.on_line('TAP 99999999')
        self.assertEqual(self.port.written, ['RES UNKNOWN'])

    def test_server_down_sends_nothing_for_a_tap(self):
        self.with_api(requests.ConnectionError('refused'))
        self.bridge.on_line('TAP E5734107')
        self.assertEqual(self.port.written, [])

    def test_late_answer_is_not_sent(self):
        self.with_api({'result': 'PAID', 'fare': 50, 'balance': 450})
        with mock.patch.object(bridge.time, 'monotonic', side_effect=[100.0, 102.5]):
            self.bridge.on_line('TAP E5734107')
        self.assertEqual(self.port.written, [])

    def test_lines_for_people_are_ignored(self):
        api = self.with_api({})
        for line in ('Card: E5734107', 'PAID KSh 50 (Campus shuttle)  |  Balance: KSh 450', 'Server: linked', ''):
            self.bridge.on_line(line)
        api.assert_not_called()
        self.assertEqual(self.port.written, [])

    def test_poll_passes_lines_on_then_sends_link(self):
        self.with_api({'lines': ['MSG Top-up +100|Bal: KSh 130', 'FARE 70']})
        self.bridge.poll_once()
        self.assertEqual(self.port.written, ['MSG Top-up +100|Bal: KSh 130', 'FARE 70', 'LINK'])

    def test_poll_with_server_down_sends_no_link(self):
        self.with_api(requests.ConnectionError('refused'))
        self.bridge.poll_once()
        self.assertEqual(self.port.written, [])
        self.assertFalse(self.bridge.server_up)

    def test_nothing_is_sent_before_ready(self):
        self.bridge.ready = False
        api = self.with_api({'lines': ['trip']})
        self.bridge.poll_once()
        api.assert_not_called()
        self.assertEqual(self.port.written, [])


if __name__ == '__main__':
    unittest.main()
