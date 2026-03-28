"""camera_permission 유틸리티 단위 테스트."""
import sys
import unittest
from unittest.mock import patch, MagicMock


class TestGetStatus(unittest.TestCase):
    def test_non_macos_returns_authorized(self):
        """비-macOS 플랫폼에서는 AUTHORIZED(3) 반환."""
        with patch.object(sys, 'platform', 'win32'):
            import importlib, camera_permission
            importlib.reload(camera_permission)
            self.assertEqual(camera_permission.get_status(), 3)

    def test_ctypes_failure_returns_authorized(self):
        """ctypes 로드 실패 시 AUTHORIZED(3) 반환 (폴백)."""
        with patch('camera_permission._load_objc', return_value=None):
            import camera_permission
            self.assertEqual(camera_permission.get_status(), 3)


class TestEnsureCameraPermission(unittest.TestCase):
    def test_non_macos_returns_true(self):
        """비-macOS에서는 True 반환."""
        with patch.object(sys, 'platform', 'win32'):
            import importlib, camera_permission
            importlib.reload(camera_permission)
            self.assertTrue(camera_permission.ensure_camera_permission())

    def test_authorized_returns_true_without_request(self):
        """이미 authorized(3)이면 request_access 호출 없이 True 반환."""
        with patch('camera_permission.get_status', return_value=3), \
             patch('camera_permission.request_access') as mock_req:
            import camera_permission
            result = camera_permission.ensure_camera_permission()
            self.assertTrue(result)
            mock_req.assert_not_called()

    def test_denied_returns_false_without_request(self):
        """denied(2)이면 request_access 호출 없이 False 반환."""
        with patch('camera_permission.get_status', return_value=2), \
             patch('camera_permission.request_access') as mock_req:
            import camera_permission
            result = camera_permission.ensure_camera_permission()
            self.assertFalse(result)
            mock_req.assert_not_called()

    def test_restricted_returns_false_without_request(self):
        """restricted(1)이면 False 반환."""
        with patch('camera_permission.get_status', return_value=1):
            import camera_permission
            self.assertFalse(camera_permission.ensure_camera_permission())

    def test_ctypes_failure_in_ensure_returns_true(self):
        """ensure_camera_permission 내부 ctypes 실패 시 True 반환 (폴백)."""
        with patch('camera_permission.get_status', side_effect=Exception("ctypes fail")):
            import camera_permission
            result = camera_permission.ensure_camera_permission()
            self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
