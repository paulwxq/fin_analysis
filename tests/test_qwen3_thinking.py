import os
import base64
from openai import OpenAI
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def test_thinking_mode():
    api_key = os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    
    if not api_key:
        print("Error: DASHSCOPE_API_KEY not found.")
        return

    # 初始化OpenAI客户端
    client = OpenAI(
        api_key=api_key,
        base_url=base_url
    )

    # 读取本地图片
    image_path = "output/600482.SH_kline.png" # 使用您刚才日志里分析的那张图
    if not os.path.exists(image_path):
        # 尝试找任意一张存在的图
        import glob
        files = glob.glob("output/*_kline.png")
        if files:
            image_path = files[0]
        else:
            print("Error: No K-line image found in output/")
            return

    print(f"Testing with image: {image_path}")

    with open(image_path, "rb") as f:
        image_data = base64.b64encode(f.read()).decode('utf-8')
    image_uri = f"data:image/png;base64,{image_data}"

    print(f"Connecting to model: qwen3-vl-plus with enable_thinking=True...")

    # 创建聊天完成请求
    try:
        completion = client.chat.completions.create(
            model="qwen3-vl-plus",
            messages=[
                {
                    "role": "system",
                    "content": """你是一位拥有20年经验的华尔街技术分析师，精通威科夫操盘法（Wyckoff Method）。
你的任务是分析上传的A股月线K线图，判断该股票是否符合"长期超跌后的底部沉淀"（Stage 1 Base）形态。
请按照评分标准(0-10分)进行详细推理。""",
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": image_uri},
                        },
                        {"type": "text", "text": "请分析这张图表，并返回JSON格式结果，包含score, reasoning等字段。"},
                    ],
                },
            ],
            stream=True,
            # 关键参数：开启思考过程
            extra_body={
                'enable_thinking': True,
                "thinking_budget": 4096  # 设置一个适中的思考预算
            }
        )

        reasoning_content = ""
        answer_content = ""
        is_answering = False

        print("\n" + "=" * 20 + " 思考过程 (Thinking Process) " + "=" * 20 + "\n")

        for chunk in completion:
            if not chunk.choices:
                continue
            
            delta = chunk.choices[0].delta
            
            # 处理思考过程
            if hasattr(delta, 'reasoning_content') and delta.reasoning_content is not None:
                print(delta.reasoning_content, end='', flush=True)
                reasoning_content += delta.reasoning_content
            else:
                # 开始回复
                if delta.content and not is_answering:
                    print("\n\n" + "=" * 20 + " 最终回复 (Final Answer) " + "=" * 20 + "\n")
                    is_answering = True
                
                if delta.content:
                    print(delta.content, end='', flush=True)
                    answer_content += delta.content

        print("\n\n" + "=" * 50)

    except Exception as e:
        print(f"\nError occurred: {e}")

if __name__ == "__main__":
    test_thinking_mode()
