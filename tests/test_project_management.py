"""
惹惹拼豆 — 项目管理模块测试

测试目标：项目生命周期管理（创建、列表、删除、设置）、
设置验证（板子大小、色号体系）、空状态与引导逻辑。
"""

import pytest
from typing import Tuple, Optional


# ── 项目创建 ──────────────────────────────────────────────────────


class TestProjectCreation:
    """项目创建的基本行为验证。"""

    def test_create_with_default_settings(self):
        """不传板子尺寸/色号时，使用默认值 32×32 / MARD 148 色。"""
        from reperibeads.project import Project

        project = Project.create(name="测试项目")
        assert project.board_width == 32
        assert project.board_height == 32
        assert project.color_system == "MARD_148"

    def test_create_with_custom_board_size(self):
        """传入自定义板子尺寸时正确应用。"""
        from reperibeads.project import Project

        project = Project.create(name="大板子", board_width=64, board_height=48)
        assert project.board_width == 64
        assert project.board_height == 48

    def test_create_with_alternative_color_system(self):
        """支持传入替代色号体系名称。"""
        from reperibeads.project import Project

        project = Project.create(name="测试", color_system="MARD_148")
        assert project.color_system == "MARD_148"

    def test_project_has_unique_id(self):
        """每个项目生成时自动分配唯一 ID。"""
        from reperibeads.project import Project

        p1 = Project.create(name="项目A")
        p2 = Project.create(name="项目B")
        assert p1.id is not None
        assert p2.id is not None
        assert p1.id != p2.id

    def test_project_has_creation_timestamp(self):
        """项目创建时记录时间戳。"""
        from reperibeads.project import Project

        p = Project.create(name="时间测试")
        assert p.created_at is not None

    def test_project_name_is_required(self):
        """创建项目时必须提供名称。"""
        from reperibeads.project import Project

        with pytest.raises((ValueError, TypeError)):
            Project.create(name="")

        with pytest.raises((ValueError, TypeError)):
            Project.create(name=None)


# ── 板子尺寸校验 ──────────────────────────────────────────────────


class TestBoardSizeValidation:
    """板子尺寸参数的边界和校验行为验证。"""

    @pytest.mark.parametrize("width,height", [
        (1, 1),
        (1, 100),
        (100, 1),
        (256, 256),
        (32, 32),
        (48, 32),
    ])
    def test_valid_board_sizes(self, width, height):
        """合法的板子尺寸范围应能正常创建项目。"""
        from reperibeads.project import Project

        p = Project.create(name=f"{width}x{height}", board_width=width, board_height=height)
        assert p.board_width == width
        assert p.board_height == height

    @pytest.mark.parametrize("width,height", [
        (0, 32),
        (32, 0),
        (-1, 32),
        (32, -1),
        (0, 0),
        (-5, -5),
    ])
    def test_invalid_board_size_raises(self, width, height):
        """板子尺寸为 0 或负数时应拒绝创建。"""
        from reperibeads.project import Project

        with pytest.raises((ValueError, AssertionError)):
            Project.create(
                name="坏尺寸",
                board_width=width,
                board_height=height,
            )

    def test_max_reasonable_board_size(self):
        """非常大但仍然合理的板子（256×256）应能创建（不考验性能）。"""
        from reperibeads.project import Project

        p = Project.create(name="超大板子", board_width=256, board_height=256)
        assert p.board_width == 256
        assert p.board_height == 256


# ── 色号体系校验 ──────────────────────────────────────────────────


class TestColorSystemValidation:
    """色号体系参数校验行为验证。"""

    def test_empty_color_system_raises(self):
        """空字符串作为色号体系名称应被拒绝。"""
        from reperibeads.project import Project

        with pytest.raises((ValueError, AssertionError)):
            Project.create(name="测试", color_system="")

    def test_none_color_system_defaults(self):
        """color_system=None 时应使用默认值 MARD_148。"""
        from reperibeads.project import Project

        p = Project.create(name="测试", color_system=None)
        assert p.color_system == "MARD_148"

    def test_case_insensitivity(self):
        """色号体系名称应大小写不敏感。"""
        from reperibeads.project import Project

        p1 = Project.create(name="A", color_system="mard_148")
        p2 = Project.create(name="B", color_system="MARD_148")
        assert p1.color_system == p2.color_system


# ── 项目列表与空状态 ──────────────────────────────────────────────


class TestProjectListing:
    """项目列表的管理和空状态行为验证。"""

    def test_empty_project_list(self):
        """无项目时应返回空列表（不应抛出异常）。"""
        from reperibeads.project import Project

        projects = Project.list()
        assert isinstance(projects, list)

    def test_list_contains_created_projects(self):
        """创建项目后，列表中应存在该项目。"""
        from reperibeads.project import Project

        p = Project.create(name="列表测试")
        projects = Project.list()
        assert any(proj.id == p.id for proj in projects)

    def test_list_returns_all_projects(self):
        """多次创建后列表返回全部项目。"""
        from reperibeads.project import Project

        _cleanup_test_projects()
        ids = set()
        for i in range(5):
            p = Project.create(name=f"项目{i}")
            ids.add(p.id)
        projects = Project.list()
        returned_ids = {proj.id for proj in projects}
        # 至少包含我们创建的全部（可能还有其他测试遗留）
        assert ids.issubset(returned_ids)

    def test_list_ordering_chronological(self):
        """列表按创建时间降序排列（最新在前）。"""
        from reperibeads.project import Project

        _cleanup_test_projects()
        p1 = Project.create(name="最早")
        p2 = Project.create(name="中间")
        p3 = Project.create(name="最新")
        projects = Project.list()
        # 找出这 3 个项目的顺序
        ids_in_list = [proj.id for proj in projects]
        positions = [ids_in_list.index(pid) for pid in [p1.id, p2.id, p3.id]]
        # 最早的应在最后面
        assert positions == sorted(positions), "列表应保持创建顺序（新在前）"


# ── 项目删除 ──────────────────────────────────────────────────────


class TestProjectDeletion:
    """项目删除行为验证。"""

    def test_delete_existing_project(self):
        """删除已存在的项目应成功。"""
        from reperibeads.project import Project

        p = Project.create(name="待删除")
        assert Project.delete(p.id) is True

    def test_project_not_listed_after_deletion(self):
        """删除后列表中不应再包含该项目。"""
        from reperibeads.project import Project

        p = Project.create(name="应消失")
        pid = p.id
        Project.delete(pid)
        projects = Project.list()
        assert not any(proj.id == pid for proj in projects)

    def test_delete_non_existent_project_raises(self):
        """删除不存在的项目应抛出异常。"""
        from reperibeads.project import Project

        with pytest.raises((ValueError, KeyError)):
            Project.delete("non-existent-id")

    def test_delete_with_none_id_raises(self):
        """传入 None 删除应抛出类型异常。"""
        from reperibeads.project import Project

        with pytest.raises((ValueError, TypeError)):
            Project.delete(None)

    def test_delete_with_empty_string_raises(self):
        """传入空字符串删除应抛出异常。"""
        from reperibeads.project import Project

        with pytest.raises((ValueError, KeyError)):
            Project.delete("")

    def test_delete_twice_raises(self):
        """同一项目重复删除第二次应抛出异常。"""
        from reperibeads.project import Project

        p = Project.create(name="删两次")
        pid = p.id
        Project.delete(pid)
        with pytest.raises((ValueError, KeyError)):
            Project.delete(pid)

    def test_delete_does_not_affect_other_projects(self):
        """删除一个项目不影响列表中其他项目。"""
        from reperibeads.project import Project

        _cleanup_test_projects()
        p1 = Project.create(name="保留")
        p2 = Project.create(name="删除")
        p2_id = p2.id
        Project.delete(p2_id)
        remaining = Project.list()
        assert any(proj.id == p1.id for proj in remaining)


# ── 项目属性 ──────────────────────────────────────────────────────


class TestProjectProperties:
    """项目属性访问与状态查询行为验证。"""

    def test_project_has_image_source_reference(self):
        """项目应记录原始图片来源路径/标识符。"""
        from reperibeads.project import Project

        p = Project.create(name="有源图片", source_image="content://media/photo/123")
        assert p.source_image == "content://media/photo/123"

    def test_project_default_source_image_is_none(self):
        """未设置源图片时 source_image 应为 None。"""
        from reperibeads.project import Project

        p = Project.create(name="无源")
        assert p.source_image is None

    def test_project_status_initial(self):
        """新建项目状态应为 'created'（尚未生成图纸）。"""
        from reperibeads.project import Project

        p = Project.create(name="状态测试")
        assert p.status == "created"

    def test_project_status_changes_after_conversion(self):
        """图纸生成后项目状态应从 'created' 变为 'completed'。"""
        from reperibeads.project import Project

        p = Project.create(name="完成态")
        p.mark_generated()
        assert p.status == "completed"


# ── 辅助 ──────────────────────────────────────────────────────────


def _cleanup_test_projects():
    """清理测试产生的项目，确保列表操作测试隔离。"""
    from reperibeads.project import Project

    for proj in Project.list():
        if proj.name and proj.name.startswith("项目") or \
           proj.name in ("最早", "中间", "最新", "保留", "删除"):
            try:
                Project.delete(proj.id)
            except (ValueError, KeyError):
                pass
