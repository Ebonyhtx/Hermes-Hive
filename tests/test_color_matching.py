"""
惹惹拼豆 — 颜色匹配模块测试

测试目标：将任意 RGB 颜色量化为标准拼豆色板中最接近的色号。
核心功能：色差计算、最近色搜索、调色板有效性。
"""

import pytest
from typing import List, Tuple


# ── 辅助构造 ──────────────────────────────────────────────────────


def _make_palette(colors: List[Tuple[int, int, int]]) -> List[Tuple[int, int, int]]:
    """构造一个简单的 RGB 调色板用于测试。"""
    return colors


# ── 色差计算 ──────────────────────────────────────────────────────


class TestColorDistance:
    """色差度量函数的行为验证。"""

    def test_identical_colors_distance_zero(self):
        """同一颜色之间的色差应为 0。"""
        from reperibeads.colors import color_distance

        assert color_distance((128, 64, 32), (128, 64, 32)) == 0.0

    def test_distinct_colors_distance_positive(self):
        """不同颜色之间的色差应大于 0。"""
        from reperibeads.colors import color_distance

        d = color_distance((0, 0, 0), (255, 255, 255))
        assert d > 0

    def test_distance_symmetric(self):
        """色差计算应满足对称性：d(a,b) == d(b,a)。"""
        from reperibeads.colors import color_distance

        a, b = (100, 200, 50), (30, 180, 220)
        assert color_distance(a, b) == color_distance(b, a)

    def test_distance_non_negative(self):
        """任意颜色对的色差值不应为负数。"""
        from reperibeads.colors import color_distance

        import random
        for _ in range(100):
            c1 = tuple(random.randint(0, 255) for _ in range(3))
            c2 = tuple(random.randint(0, 255) for _ in range(3))
            assert color_distance(c1, c2) >= 0

    def test_distance_triangle_inequality(self):
        """满足三角不等式：d(a,c) <= d(a,b) + d(b,c)。"""
        from reperibeads.colors import color_distance

        a, b, c = (255, 0, 0), (0, 255, 0), (0, 0, 255)
        d_ac = color_distance(a, c)
        d_ab = color_distance(a, b)
        d_bc = color_distance(b, c)
        assert d_ac <= d_ab + d_bc + 1e-9  # 浮点容差

    @pytest.mark.parametrize("invalid_rgb", [
        (-1, 0, 0),
        (256, 0, 0),
        (0, -1, 128),
        (0, 0, 300),
        (128,),
        (128, 128),
        (128, 128, 128, 0),
    ])
    def test_invalid_rgb_input_raises(self, invalid_rgb):
        """传入无效 RGB 值（范围外或维度错误）应抛出异常。"""
        from reperibeads.colors import color_distance

        with pytest.raises((ValueError, TypeError)):
            color_distance(invalid_rgb, (0, 0, 0))


# ── 最近色搜索 ────────────────────────────────────────────────────


class TestFindNearestColor:
    """在调色板中查找最近色号的行为验证。"""

    def test_exact_match_returns_correct_index(self):
        """调色板中存在精确匹配时，返回该色号对应的索引。"""
        from reperibeads.colors import find_nearest_color

        palette = _make_palette([
            (255, 0, 0),    # 0: 红
            (0, 255, 0),    # 1: 绿
            (0, 0, 255),    # 2: 蓝
            (255, 255, 0),  # 3: 黄
        ])
        assert find_nearest_color((0, 255, 0), palette) == 1

    def test_near_color_matches_closest(self):
        """目标颜色与调色板中某色最接近时，返回该色号索引。"""
        from reperibeads.colors import find_nearest_color

        palette = _make_palette([
            (255, 0, 0),    # 0: 纯红
            (200, 0, 0),    # 1: 暗红
            (100, 0, 0),    # 2: 深红
        ])
        # (210, 5, 5) 应接近索引 1
        assert find_nearest_color((210, 5, 5), palette) == 1

    def test_single_color_palette(self):
        """调色板只有一种颜色时，任何输入都应返回索引 0。"""
        from reperibeads.colors import find_nearest_color

        palette = _make_palette([(128, 128, 128)])
        assert find_nearest_color((0, 0, 0), palette) == 0
        assert find_nearest_color((255, 255, 255), palette) == 0
        assert find_nearest_color((255, 0, 0), palette) == 0

    def test_all_black_and_all_white_palette(self):
        """极简双色调色板：全黑(0,0,0)与全白(255,255,255)的最近色判定。"""
        from reperibeads.colors import find_nearest_color

        palette = _make_palette([
            (0, 0, 0),          # 0: 黑
            (255, 255, 255),    # 1: 白
        ])
        assert find_nearest_color((0, 0, 0), palette) == 0
        assert find_nearest_color((255, 255, 255), palette) == 1
        assert find_nearest_color((10, 10, 10), palette) == 0
        assert find_nearest_color((240, 240, 240), palette) == 1

    def test_equidistant_picks_first(self):
        """当输入颜色与调色板中多色等距离时，应选择索引最小的那个（确定性行为）。"""
        from reperibeads.colors import find_nearest_color

        # 对称场景：(0,0,0) 与 (0,0,0) 和 (0,0,100) 距离中心点不等；构造等距
        palette = _make_palette([
            (0, 0, 50),   # 0
            (0, 0, 150),  # 1
        ])
        # (0, 0, 100) 到两个的距离应该相等
        idx = find_nearest_color((0, 0, 100), palette)
        assert idx == 0  # 等距时选择索引更小的

    def test_empty_palette_raises(self):
        """空调色板应抛出异常，无法匹配任何颜色。"""
        from reperibeads.colors import find_nearest_color

        with pytest.raises(ValueError, match="empty"):
            find_nearest_color((128, 128, 128), [])

    def test_palette_input_must_be_list_of_rgb_tuples(self):
        """非法的调色板格式应抛出类型异常。"""
        from reperibeads.colors import find_nearest_color

        with pytest.raises(TypeError):
            find_nearest_color((128, 128, 128), "not_a_list")

    @pytest.mark.parametrize("invalid_rgb", [
        (-5, 0, 0), (0, 300, 0), (128, 128),
    ])
    def test_invalid_target_rgb_raises(self, invalid_rgb):
        """输入目标颜色 RGB 范围外或维度错误时抛出异常。"""
        from reperibeads.colors import find_nearest_color

        palette = _make_palette([(0, 0, 0), (255, 255, 255)])
        with pytest.raises((ValueError, TypeError)):
            find_nearest_color(invalid_rgb, palette)


# ── MARD 148 调色板 ──────────────────────────────────────────────


class TestMARD148Palette:
    """MARD 148 色标准调色板的完整性验证。"""

    def test_mard_148_has_exactly_148_colors(self):
        """MARD 148 色号体系应包含 148 种颜色。"""
        from reperibeads.colors import MARD_148

        assert len(MARD_148) == 148

    def test_mard_148_colors_are_valid_rgb_tuples(self):
        """MARD 148 中每个色号均为有效的 (R, G, B) 三元组，值在 0~255 范围内。"""
        from reperibeads.colors import MARD_148

        for i, color in enumerate(MARD_148):
            assert isinstance(color, tuple), f"索引 {i} 不是 tuple"
            assert len(color) == 3, f"索引 {i} 长度不为 3"
            r, g, b = color
            assert 0 <= r <= 255, f"索引 {i} R 值 {r} 超出范围"
            assert 0 <= g <= 255, f"索引 {i} G 值 {g} 超出范围"
            assert 0 <= b <= 255, f"索引 {i} B 值 {b} 超出范围"

    def test_mard_148_contains_no_duplicates(self):
        """MARD 148 中不应包含重复色号。"""
        from reperibeads.colors import MARD_148

        assert len(MARD_148) == len(set(MARD_148)), "调色板中存在重复色号"

    def test_find_nearest_with_mard_148(self):
        """使用完整 MARD 148 调色板执行最近色查找不抛异常。"""
        from reperibeads.colors import find_nearest_color, MARD_148

        # 随机测试几个常见颜色都能找到匹配
        test_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255),
                       (255, 255, 255), (0, 0, 0), (128, 128, 128)]
        for c in test_colors:
            idx = find_nearest_color(c, MARD_148)
            assert 0 <= idx < 148, f"颜色 {c} 返回的索引 {idx} 超出范围"

    def test_mard_148_use_default_palette(self):
        """find_nearest_color 不传 palette 参数时默认使用 MARD_148。"""
        from reperibeads.colors import find_nearest_color, MARD_148

        with_default = find_nearest_color((200, 100, 50))
        with_explicit = find_nearest_color((200, 100, 50), MARD_148)
        assert with_default == with_explicit
