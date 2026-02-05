"""工具基类模块。

定义 Agent 工具的抽象基类，所有具体工具必须继承此类：

核心属性（子类必须实现）：
- name: 工具名称（用于函数调用）
- description: 工具描述（供 LLM 理解工具用途）
- parameters: JSON Schema 格式的参数定义
- execute(): 执行工具逻辑

工具能力：
- 参数验证：validate_params() 基于 JSON Schema 验证
- Schema 转换：to_schema() 转换为 OpenAI 函数调用格式
- 异步执行：execute() 支持异步操作
"""

from abc import ABC, abstractmethod
from typing import Any


class Tool(ABC):
    """工具抽象基类。

    所有 Agent 工具的基类，提供统一的接口和功能：

    工具定义需要实现：
    1. name: 工具唯一名称（如 "read_file"）
    2. description: 工具功能描述（帮助 LLM 理解何时使用）
    3. parameters: JSON Schema 参数定义（控制 LLM 传入的参数）
    4. execute(): 工具执行逻辑（异步）

    使用示例：
        class ReadFileTool(Tool):
            @property
            def name(self) -> str:
                return "read_file"

            @property
            def description(self) -> str:
                return "读取文件内容"

            @property
            def parameters(self) -> dict[str, Any]:
                return {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "文件路径"}
                    },
                    "required": ["path"]
                }

            async def execute(self, path: str) -> str:
                # 实现逻辑
                pass
    """

    # 类型映射：JSON Schema 类型 -> Python 类型
    _TYPE_MAP = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
    }
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称。

        Returns:
            工具唯一标识符，推荐使用 snake_case 格式
        """
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述。

        供 LLM 理解工具的用途和使用场景。
        建议包含：
        - 工具能做什么
        - 何时使用
        - 注意事项

        Returns:
            描述文本
        """
        pass
    
    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """工具参数定义（JSON Schema 格式）。

        定义工具接受的参数，包括：
        - type: 参数类型（object/string/integer 等）
        - properties: 各参数定义
        - required: 必填参数列表

        Returns:
            JSON Schema 对象
        """
        pass
    
    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        """执行工具逻辑。

        子类实现具体的工具功能。

        Args:
            **kwargs: 从 parameters 中定义的参数

        Returns:
            工具执行结果，字符串格式
        """
        pass

    def validate_params(self, params: dict[str, Any]) -> list[str]:
        """验证参数是否符合 JSON Schema。

        检查项目：
        - 类型检查：string/integer/number/boolean/array/object
        - 枚举检查：enum 定义的合法值
        范围检查：minimum/maximum/minLength/maxLength
        - 必填检查：required 字段
        - 嵌套检查：object 和 array 的递归验证

        Args:
            params: 待验证的参数字典

        Returns:
            错误列表，空列表表示验证通过
        """
        schema = self.parameters or {}
        if schema.get("type", "object") != "object":
            raise ValueError(f"Schema must be object type, got {schema.get('type')!r}")
        return self._validate(params, {**schema, "type": "object"}, "")

    def _validate(self, val: Any, schema: dict[str, Any], path: str) -> list[str]:
        """递归验证参数。

        Args:
            val: 要验证的值
            schema: JSON Schema 定义
            path: 当前路径（用于错误信息）

        Returns:
            错误列表
        """
        t, label = schema.get("type"), path or "parameter"
        # 类型检查
        if t in self._TYPE_MAP and not isinstance(val, self._TYPE_MAP[t]):
            return [f"{label} should be {t}"]
        
        errors = []
        # 枚举检查
        if "enum" in schema and val not in schema["enum"]:
            errors.append(f"{label} must be one of {schema['enum']}")
        # 数值范围检查
        if t in ("integer", "number"):
            if "minimum" in schema and val < schema["minimum"]:
                errors.append(f"{label} must be >= {schema['minimum']}")
            if "maximum" in schema and val > schema["maximum"]:
                errors.append(f"{label} must be <= {schema['maximum']}")
        # 字符串长度检查
        if t == "string":
            if "minLength" in schema and len(val) < schema["minLength"]:
                errors.append(f"{label} must be at least {schema['minLength']} chars")
            if "maxLength" in schema and len(val) > schema["maxLength"]:
                errors.append(f"{label} must be at most {schema['maxLength']} chars")
        # 对象检查
        if t == "object":
            props = schema.get("properties", {})
            for k in schema.get("required", []):
                if k not in val:
                    errors.append(f"missing required {path + '.' + k if path else k}")
            for k, v in val.items():
                if k in props:
                    errors.extend(self._validate(v, props[k], path + '.' + k if path else k))
        # 数组检查
        if t == "array" and "items" in schema:
            for i, item in enumerate(val):
                errors.extend(self._validate(item, schema["items"], f"{path}[{i}]" if path else f"[{i}]"))
        return errors
    
    def to_schema(self) -> dict[str, Any]:
        """转换为 OpenAI 函数调用格式。

        Returns:
            OpenAI 格式的工具定义，可直接传给 LLM
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }
