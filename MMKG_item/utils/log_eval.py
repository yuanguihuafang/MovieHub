"""
日志解析工具 - 从训练日志中提取评估指标
使用：
    python train.py 2>&1 | python log_eval.py
    或者：
    cd MMKG_item/log
    type log.txt | python ../utils/log_eval.py
输出格式：
    指标之间用制表符分隔，方便复制到Excel等工具
"""
import sys

def parse_metrics():
    # 遍历标准输入的每一行
    for line in sys.stdin:
        line = line.strip()
        # 按冒号分割
        line = line.split(":")
        ans = []
        # 提取需要的指标（跳过第0个和第5个位置）
        for i, x in enumerate(line):
            if i in [0, 5]:
                continue
            # 提取数值的有效部分（前6个字符）
            ans.append(x[1:7])
        # 输出用制表符分隔的结果
        print("\t".join(ans))

if __name__ == "__main__":
    parse_metrics()
