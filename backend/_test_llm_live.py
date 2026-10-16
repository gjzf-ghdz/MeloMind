"""测试智谱 GLM 真实调用"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from llm_engine import LLMEngine

e = LLMEngine()
print('key:', 'configured' if e.api_key else 'MISSING', '| model:', e.model)

tests = [
    '我在打三角洲行动，想听英文歌',
    '深夜复习高数，特别焦虑，来点中文歌',
    '刚健身完心情很好',
    '开黑输了有点烦，别推中文歌',
]
for m in tests:
    r = e.analyze_user_state(m)
    print(f"{m!r} -> task={r['task_type']} emo={r['emotion']} "
          f"lang={r['language_preference']}")
print('DONE')
