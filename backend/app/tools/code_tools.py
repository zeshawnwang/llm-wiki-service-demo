"""
代码执行工具 - 供AI使用的代码执行功能
注意：在生产环境中需要严格限制执行环境，防止安全风险
"""
import subprocess
import tempfile
import os
from typing import Optional, Dict, Any, List
from pathlib import Path
import json


class CodeTools:
    """代码执行工具类"""
    
    # 允许执行的命令白名单
    ALLOWED_COMMANDS = ['python', 'python3', 'node', 'bash', 'sh']
    
    # 最大输出长度
    MAX_OUTPUT_LENGTH = 10000
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
    
    async def execute_python(self, code: str) -> Dict[str, Any]:
        """
        执行Python代码
        
        Args:
            code: Python代码字符串
            
        Returns:
            执行结果字典
        """
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_file = f.name
            
            # 执行代码
            result = subprocess.run(
                ['python', temp_file],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            
            # 清理临时文件
            os.unlink(temp_file)
            
            return {
                "success": result.returncode == 0,
                "stdout": self._truncate_output(result.stdout),
                "stderr": self._truncate_output(result.stderr),
                "returncode": result.returncode
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"代码执行超时（超过{self.timeout}秒）",
                "returncode": -1
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行错误: {str(e)}",
                "returncode": -1
            }
    
    async def execute_command(self, command: str, cwd: Optional[str] = None) -> Dict[str, Any]:
        """
        执行shell命令（受限制的）
        
        Args:
            command: 命令字符串
            cwd: 工作目录
            
        Returns:
            执行结果字典
        """
        # 安全检查：解析命令
        parts = command.split()
        if not parts:
            return {
                "success": False,
                "stdout": "",
                "stderr": "空命令",
                "returncode": -1
            }
        
        base_cmd = parts[0]
        
        # 检查是否在白名单中
        if base_cmd not in self.ALLOWED_COMMANDS:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"命令 '{base_cmd}' 不在允许列表中。允许的命令: {', '.join(self.ALLOWED_COMMANDS)}",
                "returncode": -1
            }
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=cwd
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": self._truncate_output(result.stdout),
                "stderr": self._truncate_output(result.stderr),
                "returncode": result.returncode
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"命令执行超时（超过{self.timeout}秒）",
                "returncode": -1
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"执行错误: {str(e)}",
                "returncode": -1
            }
    
    async def analyze_data(self, data: str, analysis_type: str = "summary") -> Dict[str, Any]:
        """
        使用Python分析数据
        
        Args:
            data: 数据字符串（JSON、CSV等）
            analysis_type: 分析类型（summary, stats, visualize）
            
        Returns:
            分析结果
        """
        if analysis_type == "summary":
            code = f'''
import json
try:
    data = json.loads("""{data}""")
    if isinstance(data, list):
        print(f"数据类型: 列表，长度: {{len(data)}}")
        if len(data) > 0:
            print(f"第一条记录: {{data[0]}}")
    elif isinstance(data, dict):
        print(f"数据类型: 字典，键: {{list(data.keys())}}")
    else:
        print(f"数据类型: {{type(data).__name__}}")
        print(f"数据: {{data}}")
except Exception as e:
    print(f"解析错误: {{e}}")
    print(f"原始数据: {{data[:200]}}...")
'''
        elif analysis_type == "stats":
            code = f'''
import json
import statistics
try:
    data = json.loads("""{data}""")
    if isinstance(data, list) and len(data) > 0:
        # 尝试提取数值
        numeric_values = []
        for item in data:
            if isinstance(item, (int, float)):
                numeric_values.append(item)
            elif isinstance(item, dict):
                for v in item.values():
                    if isinstance(v, (int, float)):
                        numeric_values.append(v)
        
        if numeric_values:
            print(f"数值统计:")
            print(f"  数量: {{len(numeric_values)}}")
            print(f"  最小值: {{min(numeric_values)}}")
            print(f"  最大值: {{max(numeric_values)}}")
            print(f"  平均值: {{statistics.mean(numeric_values):.2f}}")
            if len(numeric_values) > 1:
                print(f"  标准差: {{statistics.stdev(numeric_values):.2f}}")
        else:
            print("未找到数值数据")
    else:
        print("数据格式不支持统计")
except Exception as e:
    print(f"分析错误: {{e}}")
'''
        else:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"未知的分析类型: {analysis_type}",
                "returncode": -1
            }
        
        return await self.execute_python(code)
    
    def _truncate_output(self, output: str) -> str:
        """截断过长的输出"""
        if len(output) > self.MAX_OUTPUT_LENGTH:
            return output[:self.MAX_OUTPUT_LENGTH] + f"\n... (输出已截断，总长度: {len(output)} 字符)"
        return output
    
    # ==================== 工具描述（供AI使用） ====================
    
    @classmethod
    def get_tool_descriptions(cls) -> List[Dict[str, str]]:
        """获取工具描述"""
        return [
            {
                "name": "execute_python",
                "description": "执行Python代码，输入code字符串，返回执行结果",
                "parameters": {"code": "Python代码字符串"}
            },
            {
                "name": "execute_command",
                "description": "执行shell命令（受限制），输入command字符串",
                "parameters": {"command": "命令字符串"}
            },
            {
                "name": "analyze_data",
                "description": "分析数据，输入data和analysis_type（summary/stats）",
                "parameters": {"data": "数据字符串", "analysis_type": "分析类型"}
            }
        ]