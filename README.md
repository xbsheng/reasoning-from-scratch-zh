# Build A Reasoning Model (From Scratch) — 中文翻译

> 本仓库是 [rasbt/reasoning-from-scratch](https://github.com/rasbt/reasoning-from-scratch) 的中文汉化版本。

📖 **原书**: [Build a Reasoning Model (From Scratch)](https://mng.bz/lZ5B) by Sebastian Raschka (Manning, 2025)

## 翻译说明

- **翻译范围**: 所有 Markdown 单元格（标题、说明、注释）
- **未翻译内容**: 代码单元格、LaTeX 公式、URL 保持原样
- **技术术语**: 采用「中文(English)」格式，如：强化学习 (Reinforcement Learning)
- **翻译工具**: 使用 OpenAI 兼容 API 自动翻译，每 24 小时同步上游更新

## 章节目录

| 章节 | 主题 | 主要 Notebook |
|------|------|--------------|
| 第 2 章 | 使用预训练 LLM 生成文本 | `ch02/ch02_main.ipynb` |
| 第 3 章 | 评估推理模型 | `ch03/ch03_main.ipynb` |
| 第 4 章 | 通过推理时缩放改进推理 | `ch04/ch04_main.ipynb` |
| 第 5 章 | 通过自我精炼进行推理时缩放 | `ch05/ch05_main.ipynb` |
| 第 6 章 | 使用强化学习训练推理模型 | `ch06/ch06_main.ipynb` |
| 第 7 章 | 改进 GRPO 强化学习 | `ch07/ch07_main.ipynb` |
| 第 8 章 | 蒸馏推理模型以实现高效推理 | `ch08/ch08_main.ipynb` |
| 附录 C | Qwen3 LLM 源代码 | `appendix-C/chC_main.ipynb` |
| 附录 D | 使用更大的 LLM | `appendix-D/chD_main.ipynb` |
| 附录 E | 批处理与吞吐量导向的执行 | `appendix-E/chE_main.ipynb` |
| 附录 F | LLM 评估的常见方法 | `appendix-F/chF_main.ipynb` |
| 附录 G | 构建聊天界面 | `appendix-G/` |

## 自动同步

本仓库通过 GitHub Action 每日自动同步上游仓库的更新：

1. 每天北京时间 10:00 检查上游是否有新提交
2. 对比 `.ipynb` 文件，定位变更的 Markdown 单元格
3. 仅重新翻译**内容有变化**的单元格（增量翻译，节省 token）
4. 自动创建 PR 等待人工审核合并

```
上游更新 → 检测变更 → 增量翻译 → 生成 PR → 人工审核 → 合并
```

## 贡献翻译

欢迎提 PR 改善翻译质量！特别关注：

- 技术术语翻译是否准确
- 长句是否通顺
- 格式是否保持一致

## 致谢

感谢 [Sebastian Raschka](https://sebastianraschka.com/) 创建了这个优秀的开源教程。

## 引用

```bibtex
@book{build-llms-from-scratch-book,
  author       = {Sebastian Raschka},
  title        = {Build A Reasoning Model (From Scratch)},
  publisher    = {Manning},
  year         = {2025},
  isbn         = {9781633434677},
  url          = {https://mng.bz/lZ5B},
  github       = {https://github.com/rasbt/reasoning-from-scratch}
}
```
