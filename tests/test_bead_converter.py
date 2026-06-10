"""
惹惹拼豆 — 图片转拼豆网格模块测试

测试目标：将用户输入的图片（JPG/PNG）按照指定板子大小和色板，
输出一张拼豆网格图纸（二维色号索引矩阵）。
"""

import pytest
from typing import List, Tuple


# ── 辅助构造 ──────────────────────────────────────────────────────


def _dummy_image(width: int, height: int, fill: Tuple[int, int, int] = (128, 128, 128)):
    """构造一张纯色模拟图片对象，供测试使用。

    返回一个支持 pixel(x, y) 访问的类图片对象。
    """
    class DummyImage:
        def __init__(self):
            self.width = width
            self.height = height
            self._fill = fill
            self._pixels = {
                (x, y): fill for x in range(width) for y in range(height)
            }

        def get_pixel(self, x, y):
            return self._pixels.get((x, y), self._fill)

    return DummyImage()


def _checkerboard_image(width: int, height: int):
    """构造一张棋盘格图片（相邻像素颜色交替），测试空间映射准确性。"""
    class CheckerboardImage:
        def __init__(self):
            self.width = width
            self.height = height

        def get_pixel(self, x, y):
            return (255, 255, 255) if (x + y) % 2 == 0 else (0, 0, 0)

    return CheckerboardImage()


def _simple_palette():
    """返回一个极简调色板用于测试。"""
    return [(0, 0, 0), (255, 255, 255)]


# ── 基础转换 ──────────────────────────────────────────────────────


class TestConvertToGrid:
    """图片 → 拼豆网格的基本转换行为验证。"""

    def test_output_dimensions_match_board_size(self):
        """转换后网格的宽高应与传入的 board_size 一致。"""
        from reperibeads.converter import convert_to_grid

        img = _dummy_image(100, 100)
        grid = convert_to_grid(img, width=32, height=32)
        assert len(grid) == 32, f"行数应为 32，实际 {len(grid)}"
        assert all(len(row) == 32 for row in grid), "每列长度应为 32"

    def test_non_square_board(self):
        """支持非正方形板子尺寸，如 48×32。"""
        from reperibeads.converter import convert_to_grid

        img = _dummy_image(200, 150)
        grid = convert_to_grid(img, width=48, height=32)
        assert len(grid) == 32
        assert all(len(row) == 48 for row in grid)

    def test_1x1_minimal_board(self):
        """最小板子尺寸 1×1 可正常转换。"""
        from reperibeads.converter import convert_to_grid

        img = _dummy_image(10, 10, fill=(255, 0, 0))
        grid = convert_to_grid(img, width=1, height=1)
        assert len(grid) == 1
        assert len(grid[0]) == 1

    def test_output_indices_are_valid_palette_indices(self):
        """网格中每个值均为合法的调色板索引。"""
        from reperibeads.converter import convert_to_grid

        palette = _simple_palette()
        img = _dummy_image(64, 64, fill=(200, 200, 200))
        grid = convert_to_grid(img, width=8, height=8, palette=palette)
        for row in grid:
            for idx in row:
                assert 0 <= idx < len(palette), f"索引 {idx} 超出 Palette 范围"

    def test_uses_default_mard_148_palette(self):
        """不传 palette 时默认使用 MARD 148 色板进行量化。"""
        from reperibeads.converter import convert_to_grid

        img = _dummy_image(32, 32)
        grid = convert_to_grid(img, width=8, height=8)
        for row in grid:
            for idx in row:
                assert 0 <= idx < 148

    def test_image_larger_than_board_is_downsampled(self):
        """大图按板子尺寸缩小采样（不抛异常）。"""
        from reperibeads.converter import convert_to_grid

        img = _dummy_image(1024, 768)
        grid = convert_to_grid(img, width=32, height=32)
        assert len(grid) == 32
        assert all(len(row) == 32 for row in grid)

    def test_image_smaller_than_board_is_upsampled(self):
        """小图按板子尺寸放大采样（不抛异常）。"""
        from reperibeads.converter import convert_to_grid

        img = _dummy_image(4, 4)
        grid = convert_to_grid(img, width=32, height=32)
        assert len(grid) == 32
        assert all(len(row) == 32 for row in grid)


# ── 颜色量化正确性 ────────────────────────────────────────────────


class TestColorQuantization:
    """颜色量化到调色板的准确性和一致性验证。"""

    def test_pure_white_image_quantized_to_white(self):
        """全白图片量化后，每个格子都应为调色板中最近白色的索引。"""
        from reperibeads.converter import convert_to_grid

        palette = _simple_palette()  # 0:黑, 1:白
        img = _dummy_image(32, 32, fill=(255, 255, 255))
        grid = convert_to_grid(img, width=4, height=4, palette=palette)
        for row in grid:
            for idx in row:
                assert idx == 1, f"期望白色(索引1)，实际 {idx}"

    def test_pure_black_image_quantized_to_black(self):
        """全黑图片量化后，每个格子都应为调色板中最近黑色的索引。"""
        from reperibeads.converter import convert_to_grid

        palette = _simple_palette()
        img = _dummy_image(32, 32, fill=(0, 0, 0))
        grid = convert_to_grid(img, width=4, height=4, palette=palette)
        for row in grid:
            for idx in row:
                assert idx == 0, f"期望黑色(索引0)，实际 {idx}"

    def test_checkerboard_preserves_pattern(self):
        """棋盘格图片转换后相邻格子应具有不同色号。"""
        from reperibeads.converter import convert_to_grid

        palette = _simple_palette()
        # 2×2 棋盘格图片 → 2×2 板子
        img = _checkerboard_image(4, 4)
        grid = convert_to_grid(img, width=2, height=2, palette=palette)
        # 对角线应相同，相邻应不同
        assert grid[0][0] != grid[0][1], "(0,0) 和 (0,1) 应不同色"
        assert grid[0][0] == grid[1][1], "(0,0) 和 (1,1) 应对角线同色"
        assert grid[0][1] == grid[1][0], "(0,1) 和 (1,0) 应对角线同色"

    def test_deterministic_output(self):
        """同一输入重复多次应产生完全相同的网格。"""
        from reperibeads.converter import convert_to_grid

        palette = _simple_palette()
        img = _dummy_image(50, 50, fill=(100, 60, 200))
        result1 = convert_to_grid(img, width=8, height=8, palette=palette)
        result2 = convert_to_grid(img, width=8, height=8, palette=palette)
        assert result1 == result2, "两次转换结果应完全一致"


# ── 默认板子尺寸 ────────────────────────────────────────────────


class TestDefaultBoardSize:
    """需求规定的默认 32×32 板子行为验证。"""

    def test_default_parameters_use_32x32(self):
        """不传 width/height 时默认使用 32×32。"""
        from reperibeads.converter import convert_to_grid

        img = _dummy_image(200, 200)
        grid = convert_to_grid(img)
        assert len(grid) == 32
        assert all(len(row) == 32 for row in grid)

    def test_preview_grid_vs_export_grid_consistent(self):
        """同一输入在不同调用间（预览/导出）结果一致。"""
        from reperibeads.converter import convert_to_grid

        palette = _simple_palette()
        img = _dummy_image(64, 64, fill=(50, 100, 150))
        grid = convert_to_grid(img, width=16, height=16, palette=palette)
        grid2 = convert_to_grid(img, width=16, height=16, palette=palette)
        assert grid == grid2


# ── 参数校验 ──────────────────────────────────────────────────────


class TestParameterValidation:
    """非法参数应给出清晰的错误提示。"""

    @pytest.mark.parametrize("width,height", [
        (0, 32),
        (32, 0),
        (-1, 32),
        (32, -1),
        (0, 0),
    ])
    def test_invalid_board_size_raises(self, width, height):
        """板子尺寸为 0 或负数时应抛出异常。"""
        from reperibeads.converter import convert_to_grid

        img = _dummy_image(32, 32)
        with pytest.raises((ValueError, AssertionError)):
            convert_to_grid(img, width=width, height=height)

    def test_none_image_raises(self):
        """传入 None 图片应抛出异常。"""
        from reperibeads.converter import convert_to_grid

        with pytest.raises((ValueError, TypeError)):
            convert_to_grid(None, width=32, height=32)

    @pytest.mark.parametrize("bad_palette", [
        [],
        [(0, 0, 0)],  # 只有一种颜色技术上可用，但可被认为是合法
    ])
    def test_palette_too_small_warns_or_ok(self, bad_palette):
        """调色板元素过少（<2）时至少不抛未预期的异常（降级处理）。"""
        from reperibeads.converter import convert_to_grid

        img = _dummy_image(32, 32, fill=(100, 100, 100))
        try:
            grid = convert_to_grid(img, width=4, height=4, palette=bad_palette)
            if bad_palette:
                for row in grid:
                    for idx in row:
                        assert 0 <= idx < len(bad_palette)
        except (ValueError, TypeError):
            pass  # 允许抛出验证异常

    def test_palette_with_invalid_colors_raises(self):
        """调色板中包含非法 RGB 值时抛出异常。"""
        from reperibeads.converter import convert_to_grid

        bad_palette = [(0, 0, 0), (300, 0, 0)]
        img = _dummy_image(32, 32)
        with pytest.raises((ValueError, TypeError)):
            convert_to_grid(img, width=4, height=4, palette=bad_palette)
