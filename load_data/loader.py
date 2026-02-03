import os
import zipfile
import csv
import io
import logging
import traceback
import re
import math
from datetime import datetime

from . import config
from . import db
from . import utils

logger = logging.getLogger(__name__)

# CSV Header mapping for clarity (0-based index)
IDX_TIME = 0
IDX_CODE = 1
IDX_NAME = 2
IDX_OPEN = 3
IDX_CLOSE = 4
IDX_HIGH = 5
IDX_LOW = 6
IDX_VOL = 7
IDX_AMT = 8
IDX_PCT = 9
IDX_AMP = 10

# Expected Headers - Full Coverage
EXPECTED_HEADER_KEYWORDS = {
    IDX_TIME: "时间",
    IDX_CODE: "代码",
    IDX_NAME: "名称",
    IDX_OPEN: "开盘",
    IDX_CLOSE: "收盘",
    IDX_HIGH: "最高",
    IDX_LOW: "最低",
    IDX_VOL: "成交量",
    IDX_AMT: "成交额",
    IDX_PCT: "涨幅",
    IDX_AMP: "振幅"
}

# Regex for integer-like floats (e.g. "123.00")
RE_FLOAT_INTEGER = re.compile(r"^-?\d+\.0+$")

def clean_row_data(row):
    """
    Pure function to clean and validate a single CSV row.
    Returns: cleaned_row list
    Raises: ValueError if row is invalid/skipped
    """
    # 1. Strict Column Count
    if len(row) != 11:
        raise ValueError(f"Incorrect column count: expected 11, got {len(row)}")
    
    # 2. Validate Time Format
    time_str = row[IDX_TIME].strip()
    if not time_str:
        raise ValueError("Missing Time")
    try:
        time_clean = time_str[:19] 
        datetime.strptime(time_clean, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise ValueError(f"Invalid Time format: {time_str}")
    
    # 3. Code Check
    code_raw = row[IDX_CODE].strip()
    if not code_raw:
        raise ValueError("Missing Code")
    
    if config.STANDARDIZE_CODE:
        std_code = utils.transform_code(code_raw)
    else:
        std_code = code_raw
    
    # 4. Validate Prices (O/C/H/L)
    prices = {}
    for idx, name in [(IDX_OPEN, "Open"), (IDX_CLOSE, "Close"), 
                        (IDX_HIGH, "High"), (IDX_LOW, "Low")]:
        val = row[idx]
        if not val or val.strip() == '':
            raise ValueError(f"Missing {name} Price")
        try:
            f_val = float(val)
            if not math.isfinite(f_val):
                raise ValueError(f"Invalid {name} Price (NaN/Inf): {val}")
            prices[name] = f_val
        except ValueError as e:
            if "NaN/Inf" in str(e): raise e
            raise ValueError(f"Invalid {name} Price: {val}")
    
    # 4.1 High/Low Logic Check
    if prices["High"] < prices["Low"]:
        raise ValueError(f"Logic Error: High ({prices['High']}) < Low ({prices['Low']})")

    # 5. Validate Volume
    vol_val = row[IDX_VOL]
    clean_vol = vol_val
    if vol_val and vol_val.strip() != '':
        try:
            int_val = int(vol_val)
            if abs(int_val) > config.MAX_ABS_VOLUME:
                raise ValueError(f"Volume exceeds threshold: {int_val}")
            clean_vol = str(int_val)
        except ValueError:
            try:
                f_vol = float(vol_val)
                if not math.isfinite(f_vol):
                    raise ValueError("Volume is NaN/Inf")
                if abs(f_vol) > 9e15: 
                    raise ValueError("Volume too large for safe float conversion")
                
                if abs(f_vol) > config.MAX_ABS_VOLUME:
                    raise ValueError(f"Volume exceeds threshold: {f_vol}")

                if f_vol.is_integer():
                    clean_vol = str(int(f_vol))
                else:
                    raise ValueError("Volume is not an integer")
            except ValueError as e:
                raise ValueError(f"Invalid Volume: {vol_val} ({e})")
    
    # 6. Validate Other Numerics
    def check_threshold(val, name, limit):
        try:
            f_val = float(val)
            if not math.isfinite(f_val):
                raise ValueError(f"Invalid {name} (NaN/Inf): {val}")
            if abs(f_val) > limit:
                raise ValueError(f"{name} ({f_val}) exceeds limit ({limit})")
            return f_val
        except ValueError as e:
            if "exceeds" in str(e) or "NaN/Inf" in str(e): raise e
            raise ValueError(f"Invalid {name}: {val}")

    val_amt = row[IDX_AMT]
    if val_amt and val_amt.strip() != '':
        check_threshold(val_amt, "Amount", config.MAX_ABS_AMOUNT)
    
    val_pct = row[IDX_PCT]
    if val_pct and val_pct.strip() != '':
        check_threshold(val_pct, "ChangePct", config.MAX_ABS_CHANGE_PCT)

    val_amp = row[IDX_AMP]
    if val_amp and val_amp.strip() != '':
        check_threshold(val_amp, "Amplitude", config.MAX_ABS_AMPLITUDE)
    
    return [
        time_clean,
        std_code,
        row[IDX_NAME],
        row[IDX_OPEN],
        row[IDX_CLOSE],
        row[IDX_HIGH],
        row[IDX_LOW],
        clean_vol,
        row[IDX_AMT],
        row[IDX_PCT],
        row[IDX_AMP]
    ]

def process_zip_file(zip_path: str):
    """
    Worker function to process a single Zip file.
    """
    zip_filename = os.path.basename(zip_path)
    
    try:
        stat = os.stat(zip_path)
        file_size = stat.st_size
        last_modified = datetime.fromtimestamp(stat.st_mtime)
    except Exception as e:
        logger.error(f"[{zip_filename}] Failed to get file stats: {e}")
        return

    try:
        conn = db.get_db_connection()
    except Exception as e:
        logger.error(f"[{zip_filename}] Database connection failed: {e}")
        return
    
    status = "SUCCESS"
    skipped_count = 0
    error_msg = None
    total_rows = 0
    
    try:
        buffer = io.StringIO()
        csv_writer = csv.writer(buffer)
        buffer_count = 0
        stop_processing = False 
        
        with zipfile.ZipFile(zip_path, 'r') as z:
            csv_files = [f for f in z.namelist() if f.endswith('.csv')]
            
            for csv_file in csv_files:
                if stop_processing:
                    break

                with z.open(csv_file, 'r') as f:
                    text_io = io.TextIOWrapper(f, encoding='utf-8-sig', newline='')
                    reader = csv.reader(text_io)
                    
                    try:
                        header = next(reader)
                        for idx, keyword in EXPECTED_HEADER_KEYWORDS.items():
                            if len(header) <= idx or keyword not in header[idx]:
                                raise ValueError(f"Header mismatch at col {idx}: expected '{keyword}', got '{header[idx] if len(header)>idx else 'N/A'}'")
                    except StopIteration:
                        continue 
                    except ValueError as ve:
                        logger.error(f"[{zip_filename}] {csv_file} Header Error: {ve}")
                        error_msg = f"Header mismatch in {csv_file}: {ve}"
                        status = "FAILED"
                        stop_processing = True
                        break 
                    
                    for row_num, row in enumerate(reader, start=2):
                        total_rows += 1
                        try:
                            clean_row = clean_row_data(row)
                            csv_writer.writerow(clean_row)
                            buffer_count += 1
                        except (ValueError, IndexError) as e:
                            skipped_count += 1
                            if skipped_count <= 10: 
                                logger.warning(f"[{zip_filename}] Skipped bad row {csv_file}:{row_num}: {e}")
                            continue

                        if buffer_count >= config.BATCH_SIZE:
                            db.bulk_insert(conn, buffer)
                            conn.commit()
                            buffer.close()
                            buffer = io.StringIO()
                            csv_writer = csv.writer(buffer)
                            buffer_count = 0
            
            if not stop_processing and buffer_count > 0:
                db.bulk_insert(conn, buffer)
                conn.commit()

            if stop_processing:
                pass
            elif total_rows > 0:
                ratio = skipped_count / total_rows
                if skipped_count > config.MAX_SKIPPED_ROWS or ratio > config.MAX_SKIPPED_RATIO:
                    status = "FAILED"
                    error_msg = f"Skipped {skipped_count} lines ({ratio:.2%}). Exceeded threshold."
                elif skipped_count > 0:
                    status = "WARNING"
                    error_msg = f"Skipped {skipped_count} lines"
                else:
                    status = "SUCCESS"
            elif status != "FAILED":
                status = "SUCCESS" 
            
    except Exception as e:
        if 'conn' in locals(): conn.rollback()
        status = "FAILED"
        error_msg = str(e)
        logger.error(f"[{zip_filename}] Critical Error: {traceback.format_exc()}")
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO load_log (filename, status, skipped_lines, error_msg, processed_at, file_size, last_modified)
                    VALUES (%s, %s, %s, %s, NOW(), %s, %s)
                    ON CONFLICT (filename) 
                    DO UPDATE SET status=EXCLUDED.status, 
                                  skipped_lines=EXCLUDED.skipped_lines,
                                  error_msg=EXCLUDED.error_msg,
                                  processed_at=NOW(),
                                  file_size=EXCLUDED.file_size,
                                  last_modified=EXCLUDED.last_modified;
                """, (zip_filename, status, skipped_count, error_msg, file_size, last_modified))
            conn.commit()
        except Exception as log_err:
            logger.error(f"[{zip_filename}] Failed to write log: {log_err}")
        
        if 'conn' in locals(): conn.close()