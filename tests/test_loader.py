import unittest
from unittest.mock import patch
import math
from load_data import loader, config

class TestLoaderCleaning(unittest.TestCase):
    
    def setUp(self):
        # Base valid row
        # Time, Code, Name, Open, Close, High, Low, Vol, Amt, Pct, Amp
        self.base_row = [
            "2000-01-01 09:30:00", "sh600000", "PFYH", 
            "10.0", "10.5", "11.0", "9.0", 
            "100", "1000.0", "5.0", "2.0"
        ]

    def test_valid_row(self):
        cleaned = loader.clean_row_data(self.base_row)
        self.assertEqual(cleaned[1], "600000.SH") # Standardized
        self.assertEqual(cleaned[3], "10.0") # Open
        self.assertEqual(cleaned[7], "100") # Volume

    def test_high_low_logic(self):
        # High < Low
        row = self.base_row.copy()
        row[5] = "8.0" # High
        row[6] = "9.0" # Low
        with self.assertRaises(ValueError) as cm:
            loader.clean_row_data(row)
        self.assertIn("Logic Error: High", str(cm.exception))

    def test_volume_float_integer(self):
        # Volume 123.0 -> 123
        row = self.base_row.copy()
        row[7] = "123.0"
        cleaned = loader.clean_row_data(row)
        self.assertEqual(cleaned[7], "123")

    def test_volume_non_integer(self):
        # Volume 1.5 -> Error
        row = self.base_row.copy()
        row[7] = "1.5"
        with self.assertRaises(ValueError) as cm:
            loader.clean_row_data(row)
        self.assertIn("not an integer", str(cm.exception))

    def test_volume_large_float(self):
        # Volume 1e6 -> 1000000
        row = self.base_row.copy()
        row[7] = "1e6"
        cleaned = loader.clean_row_data(row)
        self.assertEqual(cleaned[7], "1000000")

    def test_volume_precision_unsafe(self):
        # Volume too large for float safety
        row = self.base_row.copy()
        row[7] = "1e16"
        with self.assertRaises(ValueError) as cm:
            loader.clean_row_data(row)
        self.assertIn("Volume too large", str(cm.exception))

    def test_inf_check(self):
        row = self.base_row.copy()
        row[10] = "inf" # Amplitude
        with self.assertRaises(ValueError) as cm:
            loader.clean_row_data(row)
        self.assertIn("NaN/Inf", str(cm.exception))

    def test_threshold_check(self):
        row = self.base_row.copy()
        row[9] = "20000" # ChangePct > 10000
        with self.assertRaises(ValueError) as cm:
            loader.clean_row_data(row)
        self.assertIn("exceeds limit", str(cm.exception))

    def test_amount_threshold(self):
        row = self.base_row.copy()
        row[8] = "2000000000000" # 2 Trillion
        with self.assertRaises(ValueError) as cm:
            loader.clean_row_data(row)
        self.assertIn("exceeds limit", str(cm.exception))

    def test_column_count(self):
        row = self.base_row[:-1] # 10 columns
        with self.assertRaises(ValueError):
            loader.clean_row_data(row)

if __name__ == '__main__':
    unittest.main()
