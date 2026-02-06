import akshare as ak
import pandas as pd
import warnings

# 忽略警告信息
warnings.filterwarnings("ignore")

def test_1_individual_info():
    """1. 公司基本信息 - 东方财富"""
    print(">>> 1. 正在测试: 公司基本信息 (ak.stock_individual_info_em)")
    try:
        df = ak.stock_individual_info_em(symbol="603080")
        print(df)
        print("PASS\n")
    except Exception as e:
        print(f"FAIL: {e}\n")

def test_2_yjyg():
    """2. 业绩预告 - 东方财富"""
    print(">>> 2. 正在测试: 业绩预告 (ak.stock_yjyg_em)")
    try:
        df = ak.stock_yjyg_em(date="20241231")
        print(df.head())
        print("PASS\n")
    except Exception as e:
        print(f"FAIL: {e}\n")

def test_3_sy_profile():
    """3. 商誉数据 - 东方财富"""
    print(">>> 3. 正在测试: 商誉数据 (ak.stock_sy_profile_em)")
    try:
        df = ak.stock_sy_profile_em()
        print(df.head())
        print("PASS\n")
    except Exception as e:
        print(f"FAIL: {e}\n")

def test_4_news():
    """4. 个股新闻 - 东方财富"""
    print(">>> 4. 正在测试: 个股新闻 (ak.stock_news_em)")
    try:
        df = ak.stock_news_em(symbol="603080")
        
        print(f"共获取到 {len(df)} 条新闻：\n")
        for index, row in df.iterrows():
            print(f"[{index + 1}] 标题: {row['新闻标题']}")
            print(f"    发布时间: {row['发布时间']} | 来源: {row['文章来源']}")
            print(f"    链接: {row['新闻链接']}")
            print(f"    完整内容: {row['新闻内容']}")
            print("-" * 50)
            
        print("PASS\n")
    except Exception as e:
        print(f"FAIL: {e}\n")

def test_5_sentiment_broken():
    """5. 市场情绪指数 - 数库 (已知失效)"""
    print(">>> 5. 正在测试: 市场情绪指数 (ak.index_news_sentiment_scope) [已知数据源失效]")
    try:
        df = ak.index_news_sentiment_scope()
        print(df.head())
    except Exception as e:
        print(f"Expected FAIL: 该接口数据源(DataGo)目前无法连接: {e}\n")

def test_6_hot_rank_alternative():
    """替代方案 1: 东方财富-个股人气榜"""
    print(">>> 6. [替代方案] 正在测试: 东方财富-个股人气榜 (ak.stock_hot_rank_em)")
    try:
        df = ak.stock_hot_rank_em()
        print(df.head())
        print("PASS\n")
    except Exception as e:
        print(f"FAIL: {e}\n")

def test_7_market_activity_alternative():
    """替代方案 2: 乐咕乐股-市场活跃度(情绪指标)"""
    print(">>> 7. [替代方案] 正在测试: 乐咕乐股-市场活跃度 (ak.stock_market_activity_legu)")
    try:
        df = ak.stock_market_activity_legu()
        print(df)
        print("PASS\n")
    except Exception as e:
        print(f"FAIL: {e}\n")

if __name__ == "__main__":
    print(f"AKShare 官方文档测试 (版本: {ak.__version__})\n")
    test_1_individual_info()
    test_2_yjyg()
    test_3_sy_profile()
    test_4_news()
    test_5_sentiment_broken()
    test_6_hot_rank_alternative()
    test_7_market_activity_alternative()