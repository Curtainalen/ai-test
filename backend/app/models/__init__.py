from app.models.identity import Project, ProjectMember, TestEnvironment, User
from app.models.assets import ApiImport, ApiInterface, ApiModule, ContentBlock, DebugRun, DocumentParseJob, DocumentVersion, RequirementDocument, RequirementModule
from app.models.execution import ExecutionStep, ExecutionTask, ReportStep, ScenarioStep, TestReport, TestScenario
from app.models.model_config import LlmCallRecord, ModelConfig, ModelConfigRevision
from app.models.requirement_ai import ApiScenarioCandidate, RequirementCoverage, RequirementReview, RequirementTestPoint
from app.models.ui import (LocatorVerification, UiAutomationCandidate, UiElement, UiEvidence, UiExecutionReport, UiExecutionReportStep, UiExecutionStep, UiExecutionTask, UiExplorationSession, UiExplorationStep, UiExplorationTurn, UiModule, UiPage, UiPageStep, UiPageStepDetail, UiScenario, UiScenarioStep)
from app.models.ui_collection import UiCollectedElement, UiCollectedPage, UiCollectionSession, UiCollectionSnapshot, UiLocatorCandidate, UiLocatorRevision

__all__ = ["User", "Project", "ProjectMember", "TestEnvironment", "ModelConfig", "ModelConfigRevision", "LlmCallRecord", "RequirementDocument", "DocumentVersion", "DocumentParseJob", "ContentBlock", "RequirementModule", "RequirementReview", "RequirementTestPoint", "RequirementCoverage", "ApiScenarioCandidate", "ApiImport", "ApiModule", "ApiInterface", "DebugRun", "TestScenario", "ScenarioStep", "ExecutionTask", "ExecutionStep", "TestReport", "ReportStep", "UiModule", "UiPage", "UiElement", "UiPageStep", "UiPageStepDetail", "UiScenario", "UiScenarioStep", "LocatorVerification", "UiExplorationSession", "UiExplorationStep", "UiExecutionTask", "UiExecutionStep", "UiExecutionReport", "UiExecutionReportStep", "UiEvidence", "UiAutomationCandidate"]
