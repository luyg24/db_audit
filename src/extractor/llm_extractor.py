"""
LLM内容提取模块
功能：
- 支持多种LLM Provider：Claude/OpenAI/Ollama/Trae/Custom
- 提取论文结构化信息
- 返回JSON格式结果
"""

import os
import re
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
from pathlib import Path
import httpx

logger = logging.getLogger(__name__)


# 提取Prompt模板
EXTRACTION_PROMPT = """你是一位学术论文分析专家。请分析以下论文内容，提取关键信息。

## 论文内容
{content}

## 请提取以下信息（JSON格式）

请以JSON格式返回以下字段：
1. problem: 这篇论文解决的核心问题是什么？（一句话概括）
2. method: 采用了什么主要方法或技术？（2-3句话）
3. contribution: 论文的主要贡献是什么？（列出1-3点）
4. results: 实验结果如何？有什么关键发现？
5. limitations: 论文有什么局限性？
6. future_work: 论文提到的未来工作方向
7. keywords: 5-8个关键词（数组）

请只返回JSON，不要有其他内容。"""


def resolve_env_var(value: str) -> str:
    """
    解析环境变量引用
    支持 ${ENV_VAR} 格式
    """
    if not isinstance(value, str):
        return value

    pattern = r'\$\{([^}]+)\}'
    matches = re.findall(pattern, value)

    for match in matches:
        env_value = os.getenv(match, "")
        value = value.replace(f"${{{match}}}", env_value)

    return value


class BaseLLMClient(ABC):
    """LLM客户端基类"""

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """生成回复"""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """检查客户端是否可用"""
        pass


class ClaudeClient(BaseLLMClient):
    """Claude API客户端"""

    def __init__(self, config: Dict):
        claude_config = config.get("claude", {})
        self.api_key = resolve_env_var(claude_config.get("api_key") or config.get("api_key", ""))
        self.model = claude_config.get("model", config.get("model", "claude-3-5-sonnet-20241022"))
        self.base_url = claude_config.get("base_url") or config.get("base_url")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        try:
            import anthropic

            client_kwargs = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url

            client = anthropic.Anthropic(**client_kwargs)

            kwargs = {
                "model": self.model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}]
            }

            if system_prompt:
                kwargs["system"] = system_prompt

            response = client.messages.create(**kwargs)
            return response.content[0].text

        except Exception as e:
            logger.error(f"Claude API调用失败: {e}")
            raise


class OpenAIClient(BaseLLMClient):
    """OpenAI API客户端"""

    def __init__(self, config: Dict):
        openai_config = config.get("openai", {})
        self.api_key = resolve_env_var(openai_config.get("api_key") or config.get("api_key", ""))
        self.model = openai_config.get("model", config.get("model", "gpt-4o"))
        self.base_url = openai_config.get("base_url") or config.get("base_url")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        try:
            from openai import OpenAI

            client_kwargs = {"api_key": self.api_key}
            if self.base_url:
                client_kwargs["base_url"] = self.base_url

            client = OpenAI(**client_kwargs)

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                messages=messages
            )

            return response.choices[0].message.content

        except Exception as e:
            logger.error(f"OpenAI API调用失败: {e}")
            raise


class OllamaClient(BaseLLMClient):
    """Ollama本地模型客户端"""

    def __init__(self, config: Dict):
        ollama_config = config.get("ollama", {})
        self.endpoint = ollama_config.get("endpoint", "http://localhost:11434")
        self.model = ollama_config.get("model", "llama3")

    def is_available(self) -> bool:
        try:
            with httpx.Client() as client:
                response = client.get(f"{self.endpoint}/api/tags", timeout=5)
                return response.status_code == 200
        except:
            return False

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        try:
            with httpx.Client(timeout=300) as client:
                payload = {
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                }
                if system_prompt:
                    payload["system"] = system_prompt

                response = client.post(
                    f"{self.endpoint}/api/generate",
                    json=payload
                )
                result = response.json()
                return result.get("response", "")

        except Exception as e:
            logger.error(f"Ollama调用失败: {e}")
            raise


class TraeClient(BaseLLMClient):
    """Trae IDE客户端（字节跳动）"""

    def __init__(self, config: Dict):
        trae_config = config.get("trae", {})
        self.enabled = trae_config.get("enabled", False)
        self.endpoint = trae_config.get("endpoint", "http://localhost:8080")
        self.model = trae_config.get("model", "default")

    def is_available(self) -> bool:
        if not self.enabled:
            return False
        try:
            with httpx.Client() as client:
                response = client.get(f"{self.endpoint}/health", timeout=5)
                return response.status_code == 200
        except:
            return False

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        调用Trae IDE的AI能力
        """
        try:
            with httpx.Client(timeout=300) as client:
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ]
                }
                if system_prompt:
                    payload["messages"].insert(0, {"role": "system", "content": system_prompt})

                response = client.post(
                    f"{self.endpoint}/v1/chat/completions",
                    json=payload
                )
                result = response.json()
                return result.get("choices", [{}])[0].get("message", {}).get("content", "")

        except Exception as e:
            logger.error(f"Trae调用失败: {e}")
            raise


class CustomClient(BaseLLMClient):
    """自定义API客户端（兼容OpenAI格式）"""

    def __init__(self, config: Dict):
        custom_config = config.get("custom", {})
        self.enabled = custom_config.get("enabled", False)
        self.endpoint = custom_config.get("endpoint", "http://localhost:8000/v1")
        self.model = custom_config.get("model", "custom-model")
        self.api_key = resolve_env_var(custom_config.get("api_key", ""))
        self.format = custom_config.get("format", "openai")
        self.headers = custom_config.get("headers", {})

    def is_available(self) -> bool:
        return self.enabled and bool(self.endpoint)

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            headers.update(self.headers)

            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": 4096
            }

            with httpx.Client(timeout=300) as client:
                response = client.post(
                    f"{self.endpoint}/chat/completions",
                    json=payload,
                    headers=headers
                )
                result = response.json()

                if self.format == "openai":
                    return result.get("choices", [{}])[0].get("message", {}).get("content", "")
                else:
                    # 自定义格式，根据实际返回结构调整
                    return result.get("content", result.get("response", ""))

        except Exception as e:
            logger.error(f"Custom API调用失败: {e}")
            raise


def get_llm_client(config: Dict) -> BaseLLMClient:
    """
    根据配置获取LLM客户端

    Args:
        config: LLM配置字典

    Returns:
        LLM客户端实例
    """
    provider = config.get("provider", "claude").lower()

    clients = {
        "claude": ClaudeClient,
        "openai": OpenAIClient,
        "ollama": OllamaClient,
        "trae": TraeClient,
        "custom": CustomClient
    }

    client_class = clients.get(provider)
    if not client_class:
        raise ValueError(f"不支持的LLM Provider: {provider}")

    client = client_class(config)

    if not client.is_available():
        raise RuntimeError(f"{provider} 客户端不可用，请检查配置")

    logger.info(f"使用LLM Provider: {provider}")
    return client


class LLMExtractor:
    """论文内容提取器"""

    def __init__(self, config: Dict):
        """
        初始化提取器

        Args:
            config: 完整配置字典
        """
        llm_config = config.get("llm", {})
        self.client = get_llm_client(llm_config)
        self.max_content_length = 50000  # 最大内容长度（字符）

    def extract(self, markdown_content: str) -> Dict[str, Any]:
        """
        从Markdown内容中提取结构化信息

        Args:
            markdown_content: 论文的Markdown内容

        Returns:
            提取的结构化信息字典
        """
        # 截断过长的内容
        if len(markdown_content) > self.max_content_length:
            logger.warning(f"内容过长({len(markdown_content)})，截断到{self.max_content_length}")
            markdown_content = markdown_content[:self.max_content_length]
            markdown_content += "\n\n... [内容已截断]"

        prompt = EXTRACTION_PROMPT.format(content=markdown_content)

        try:
            response = self.client.generate(prompt)

            # 解析JSON
            # 尝试从响应中提取JSON
            json_str = response.strip()

            # 如果响应包含```json代码块，提取其中的JSON
            if "```json" in json_str:
                start = json_str.find("```json") + 7
                end = json_str.find("```", start)
                json_str = json_str[start:end].strip()
            elif "```" in json_str:
                start = json_str.find("```") + 3
                end = json_str.find("```", start)
                json_str = json_str[start:end].strip()

            result = json.loads(json_str)
            logger.info("提取成功")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")
            logger.error(f"原始响应: {response[:500]}")
            return {"error": "JSON解析失败", "raw_response": response}
        except Exception as e:
            logger.error(f"提取失败: {e}")
            return {"error": str(e)}

    def extract_from_file(self, markdown_path: Path) -> Dict[str, Any]:
        """
        从Markdown文件提取结构化信息

        Args:
            markdown_path: Markdown文件路径

        Returns:
            提取的结构化信息字典
        """
        if not markdown_path.exists():
            raise FileNotFoundError(f"文件不存在: {markdown_path}")

        with open(markdown_path, "r", encoding="utf-8") as f:
            content = f.read()

        return self.extract(content)


def main():
    """测试入口"""
    import yaml

    # 加载配置
    with open("config/settings.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    try:
        extractor = LLMExtractor(config)

        # 测试提取
        test_content = """
        # A Novel Approach to Database Auditing

        ## Abstract
        This paper presents a new method for database auditing...

        ## Introduction
        Database auditing is critical for security...

        ## Method
        We propose a machine learning based approach...
        """

        result = extractor.extract(test_content)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"初始化失败: {e}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
