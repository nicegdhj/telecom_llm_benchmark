from ais_bench.benchmark.openicl.icl_evaluator import BaseEvaluator
from ais_bench.benchmark.registry import ICL_EVALUATORS
from ais_bench.benchmark.utils.logging.exceptions import AISBenchImportError
from ais_bench.benchmark.utils.logging.error_codes import UTILS_CODES
from ais_bench.benchmark.utils.logging.logger import AISLogger
logger = AISLogger()

@ICL_EVALUATORS.register_module()
class MATHEvaluator(BaseEvaluator):

    def score(self, predictions, references):
        try:
            from latex2sympy2_extended import NormalizationConfig
            from math_verify import (ExprExtractionConfig,
                                     LatexExtractionConfig, parse, verify)
        except ImportError:
            raise AISBenchImportError(
                UTILS_CODES.DEPENDENCY_MODULE_IMPORT_ERROR, 
                f"Failed to import required modules. Please install the necessary packages: pip install math_verify latex2sympy2_extended",
            )
        def verify_with_tolerance(answer_parsed, gold_parsed, tolerance=1e-3) -> bool:
            """
            带浮点数误差容忍机制的验证函数 (math_verify 包装器)
            优先使用代数符号等价校验，若不通过，则尝试将双方转化为 Python float 并比较数值误差。
            """
            # 1. 第一优先：直接利用 math_verify 原生的强符号等价验证逻辑
            try:
                if float(verify(answer_parsed, gold_parsed)):
                    return True
            except Exception:
                pass    
            # 2. 如果不相等，进入兜底分支 (Fallback) 尝试数值模糊逼近
            def _to_float(parsed_item):
                logger.info(f"========== _to_float 开始处理 ==========")
                logger.info(f"[输入数据] parsed_item: {parsed_item} (类型: {type(parsed_item)})")

                if not parsed_item:
                    logger.error("[异常] 输入的解析结果为空")
                    raise ValueError("输入的解析结果为空")
                    
                # 提取列表的第一个元素
                item = parsed_item[0] if isinstance(parsed_item, list) else parsed_item
                logger.info(f"[提取元素] item: {item} (类型: {type(item)})")
                
                # 【修复Bug】必须在 isinstance 判断前导入 sympy！
                import sympy
                
                # 场景 A: 已经是原生 int 或 float
                if isinstance(item, (int, float)):
                    logger.info(f"[命中 场景A] 原生数字类型，直接返回: {float(item)}")
                    return float(item)
                    
                # 场景 B: sympy 原生数值或代数对象
                if isinstance(item, sympy.Basic):
                    logger.info("[进入 场景B] 识别为 sympy.Basic 对象")
                    if getattr(item, 'is_number', False) or not item.free_symbols:
                        res = float(item.evalf())
                        logger.info(f"[场景B 成功] 转换为浮点数: {res}")
                        return res
                    else:
                        logger.error("[场景B 失败] 表达式内包含未处理的代数变量")
                        raise ValueError("表达式内包含未处理的代数变量，无法转为浮点数。")
      
                # 提取为纯文本
                text_val = str(item).strip()
                logger.info(f"[转为文本] 准备解析文本: '{text_val}'")
                if '\\overline{' in text_val:
                    import re
                    # 将 \overline{数字} 提取出来，并将里面的数字重复 15 次
                    # 比如 "233.\overline{3}" 会变成 "233.333333333333333"
                    text_val = re.sub(
                        r'\\overline\{([0-9]+)\}', 
                        lambda m: m.group(1) * 15, 
                        text_val
                    )
                    logger.info(f"[正则修复] 展开循环小数后变为: '{text_val}'")                
                # 场景 C: 百分号
                if text_val.endswith('%'):
                    res = float(text_val[:-1]) / 100.0
                    logger.info(f"[命中 场景C] 识别为百分比，转换结果: {res}")
                    return res
                    
                # 场景 D: latex2sympy 解析
                logger.info("[进入 场景D] 尝试使用 latex2sympy 解析...")
                try:
                    from latex2sympy2_extended import latex2sympy
                    sym_expr = latex2sympy(text_val)
                    logger.info(f"[场景D 解析结果] sympy对象: {sym_expr} (类型: {type(sym_expr)})")
                    
                    if isinstance(sym_expr, sympy.Basic):
                        if getattr(sym_expr, 'is_number', False) or not sym_expr.free_symbols:
                            res = float(sym_expr.evalf())
                            logger.info(f"[场景D 成功] latex 成功求值为浮点数: {res}")
                            return res
                        else:
                            logger.warning("[场景D 警告] 包含变量，无法求值")
                except Exception as e:
                    # 之前这里是 pass，现在打印出具体报错原因，方便抓虫
                    logger.warning(f"[场景D 失败] latex2sympy 抛出异常: {e}")
                                       
                # 场景 E: 最后的原生 float 强转
                logger.info(f"[进入 场景E] 最后的倔强，尝试原生 float('{text_val}')")
                try:
                    res = float(text_val)
                    logger.info(f"[场景E 成功] 原生 float 转换成功: {res}")
                    return res
                except Exception as e:
                    logger.error(f"[场景E 失败] 原生 float 无法转换: {e}")
                    raise # 抛出给最外层的 except 捕获
            try:
                ans_float = _to_float(answer_parsed)
                gold_float = _to_float(gold_parsed)
                # 判断两点绝对误差是否在容忍范围内
                return abs(ans_float - gold_float) < tolerance
                
            except Exception:
                # 当遇到完全风马牛不相及的格式，或 x+y、无效分数等不可强转为 float 的表达式时
                # 安全捕获异常并返回错误，不崩溃流水线
                return False
        self.is_num_equal(predictions, references)

        correct = 0
        count = 0
        details = []
        for i, j in zip(predictions, references):
            count += 1
            gold_parsed = parse(
                j,
                extraction_mode='first_match',
                extraction_config=[
                    LatexExtractionConfig(),
                    ExprExtractionConfig(),
                ],
            )
            # If parsing result is empty, try adding LaTeX
            # environment and parse again
            if len(gold_parsed) == 0:
                j_with_env = f'${j}$'
                gold_parsed = parse(
                    j_with_env,
                    extraction_mode='first_match',
                    extraction_config=[
                        LatexExtractionConfig(),
                        ExprExtractionConfig(),
                    ],
                )
            if len(gold_parsed) != 0:
                # We require the answer to be provided in correct
                # latex (no malformed operators)
                answer_parsed = parse(
                    i,
                    extraction_config=[
                        LatexExtractionConfig(
                            normalization_config=NormalizationConfig(
                                nits=False,
                                malformed_operators=False,
                                basic_latex=True,
                                equations=True,
                                boxed='all',
                                units=True,
                            ),
                            # Ensures that boxed is tried first
                            boxed_match_priority=0,
                            try_extract_without_anchor=False,
                        )
                    ],
                    extraction_mode='first_match',
                )
            
                answer_correct = float(verify_with_tolerance(answer_parsed, gold_parsed, tolerance=1e-3))
                correct += answer_correct
                detail = {
                    'pred': str(answer_parsed),
                    'answer': str(gold_parsed),
                    'correct': True if answer_correct else False,
                }
                details.append(detail)
        result = {'accuracy': 100 * correct / count, 'details': details}
        return result


if __name__ == '__main__':
    import sympy
    try:
        from math_verify import parse
    except ImportError:
        raise AISBenchImportError(
            UTILS_CODES.DEPENDENCY_MODULE_IMPORT_ERROR, 
            f"Failed to import required modules. Please install the necessary packages: pip install math_verify",
        )
    test_cases = [
        # 1. Basic arithmetic operations
        r'Simple fraction: \boxed{\frac{1}{2}}',
        r'Addition: \boxed{2 + 3}',
        r'Multiplication: \boxed{2 \times 3}',
        # 2. Algebraic expressions
        r'Quadratic: \boxed{x^2 + 2x + 1}',
        r'Polynomial: \boxed{3x^3 - 2x^2 + 4x - 5}',
        # 3. Trigonometric functions
        r'Trigonometry: \boxed{\sin(x) + \cos(x)}',
        r'Complex trig: \boxed{\tan^2(x) + \sec^2(x)}',
        # 4. Roots and exponents
        r'Square root: \boxed{\sqrt{16}}',
        r'Complex root: \boxed{\sqrt[3]{x^2 + 1}}',
        # 5. Logarithms
        r'Natural log: \boxed{\ln(e^2)}',
        r'Log base: \boxed{\log_2(8)}',
        # 6. Limits and summations
        r'Limit: \boxed{\lim_{x \to 0} \frac{\sin(x)}{x}}',
        r'Sum: \boxed{\sum_{i=1}^{n} i}',
        # 7. Integrals
        r'Integral: \boxed{\int_{0}^{1} x^2 dx}',
        r'Double integral: \boxed{\int_{0}^{1}\int_{0}^{1} xy \,dx\,dy}',
        # 8. Matrices
        r'Matrix: \boxed{\begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}}',
        # 9. Complex combinations
        r'Complex expr: \boxed{\frac{\sqrt{x^2 + 1}}{\ln(x)} + '
        r'\int_{0}^{x} t^2 dt}',
        # 10. Error cases
        r'Empty: \boxed{}',
        r'Invalid: \boxed{\frac{1}}',  # Missing denominator
        r'Nested: \boxed{\boxed{1}}',  # Nested boxed
    ]

    def print_result(expr: str, result: list):
        print('\n' + '=' * 50)
        print(f'Input: {expr}')
        print(f'Output type: {type(result)}')
        print(f'Output: {result}')

        # If result is sympy expression, show more information
        if result:
            for item in result:
                if isinstance(item, sympy.Basic):
                    print(f'Sympy repr: {repr(item)}')
                    try:
                        print(f'Evaluated: {item.evalf()}')
                    except Exception as e:
                        print(f'Cannot evaluate: {e}')

    # Test all cases
    for test_expr in test_cases:
        try:
            result = parse(test_expr)
            print_result(test_expr, result)
        except Exception as e:
            print(f'\nError processing {test_expr}: {e}')

    # Special test: verify numerical calculations
    numerical_tests = [
        r'\boxed{2 + 2}',  # Should equal 4
        r'\boxed{\frac{1}{2} + \frac{1}{3}}',  # Should equal 5/6
        r'\boxed{\sqrt{16} + \sqrt{9}}',  # Should equal 7
    ]

    print('\n' + '=' * 50 + '\nNumerical Verification Tests:')
    for test_expr in numerical_tests:
        try:
            result = parse(test_expr)
            if result and isinstance(result[0], sympy.Basic):
                expr = result[0]
                print(f'\nExpression: {test_expr}')
                print(f'Symbolic: {expr}')
                print(f'Numerical value: {float(expr.evalf())}')
        except Exception as e:
            print(f'\nError in numerical test {test_expr}: {e}')
