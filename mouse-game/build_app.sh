#!/usr/bin/env bash
# AimGuard macOS App Bundle 빌드 스크립트
# Usage: ./build_app.sh
# 결과물: dist/AimGuard.app (~500MB)

set -e
cd "$(dirname "$0")"

echo "=== 1. 이전 빌드 삭제 ==="
rm -rf build dist

echo "=== 2. py2app 빌드 ==="
python3 setup.py py2app 2>&1 | tee build.log

APP=dist/AimGuard.app/Contents/Resources/lib/python3.13
PYSIDE=$APP/PySide6
QTLIB=$PYSIDE/Qt/lib

echo "=== 3. py2app qt5 레시피가 강제 추가한 PyQt5 제거 ==="
rm -rf "$APP/PyQt5"

echo "=== 4. PySide6 미사용 개발 도구 및 QML 제거 ==="
rm -rf "$PYSIDE/Qt/qml"
rm -rf "$PYSIDE/Qt/translations"
rm -rf "$PYSIDE/Qt/metatypes"
rm -rf "$PYSIDE/qmlls"
rm -rf "$PYSIDE/qmlformat"
rm -rf "$PYSIDE/Assistant.app"
rm -rf "$PYSIDE/Linguist.app"
rm -rf "$PYSIDE/Designer.app"

echo "=== 5. 미사용 PySide6 Python 바인딩(.so) 제거 ==="
UNUSED_SO=(
    Qt3DAnimation Qt3DCore Qt3DExtras Qt3DInput Qt3DLogic Qt3DRender
    QtBluetooth QtCanvasPainter QtCharts QtConcurrent
    QtDataVisualization QtDesigner QtGraphs QtGraphsWidgets QtHelp QtHttpServer
    QtLocation QtNetworkAuth QtNfc
    QtPdf QtPdfWidgets QtPositioning
    QtQml QtQuick QtQuick3D QtQuickControls2 QtQuickTest QtQuickWidgets
    QtRemoteObjects QtScxml QtSensors QtSerialBus QtSerialPort
    QtSpatialAudio QtSql QtStateMachine QtTest QtTextToSpeech
    QtUiTools QtWebChannel QtWebEngineCore QtWebEngineQuick
    QtWebEngineWidgets QtWebSockets QtWebView
)
for mod in "${UNUSED_SO[@]}"; do
    rm -f "$PYSIDE/${mod}.abi3.so"
done

echo "=== 6. 미사용 Qt 프레임워크(.framework) 제거 ==="
UNUSED_FW=(
    Qt3DAnimation Qt3DCore Qt3DExtras Qt3DInput Qt3DLogic Qt3DRender
    Qt3DQuick Qt3DQuickAnimation Qt3DQuickExtras Qt3DQuickInput
    Qt3DQuickLogic Qt3DQuickRender Qt3DQuickScene2D Qt3DQuickScene3D
    QtBluetooth QtCanvasPainter
    QtCharts QtChartsQml QtConcurrent
    QtDataVisualization QtDataVisualizationQml
    QtDesigner QtDesignerComponents
    QtGraphs QtGraphsWidgets QtHelp QtHttpServer
    QtLocation QtNetworkAuth QtNfc
    QtPdf QtPdfWidgets QtPositioning QtPositioningQuick
    QtQml QtQmlCompiler QtQmlCore QtQmlMeta QtQmlModels
    QtQmlWorkerScript QtQmlXmlListModel
    QtQuick QtQuick3D QtQuick3DAssetImport QtQuick3DAssetUtils
    QtQuick3DGlslParser QtQuick3DHelpers QtQuick3DHelpersImpl
    QtQuick3DIblBaker QtQuick3DParticles QtQuick3DPhysics
    QtQuick3DPhysicsHelpers QtQuick3DRuntimeRender QtQuick3DXr
    QtQuickControls2 QtQuickControls2Basic QtQuickControls2BasicStyleImpl
    QtQuickControls2FluentWinUI3StyleImpl QtQuickControls2Fusion
    QtQuickControls2FusionStyleImpl QtQuickControls2Imagine
    QtQuickControls2ImagineStyleImpl QtQuickControls2Material
    QtQuickControls2MaterialStyleImpl QtQuickControls2Universal
    QtQuickControls2UniversalStyleImpl QtQuickControls2WindowsStyleImpl
    QtQuickDialogs2 QtQuickDialogs2QuickImpl QtQuickDialogs2Utils
    QtQuickEffects QtQuickLayouts QtQuickTemplates2 QtQuickTest
    QtQuickTimeline QtQuickTimelineBlendTrees QtQuickVectorImage QtQuickWidgets
    QtRemoteObjects
    QtScxml QtScxmlQml
    QtSensors QtSensorsQuick QtSerialBus QtSerialPort
    QtShaderTools QtSpatialAudio QtSql QtStateMachine QtStateMachineQml
    QtTest QtTextToSpeech QtUiTools
    QtWebChannel QtWebEngineCore QtWebEngineQuick QtWebEngineWidgets
    QtWebSockets QtWebView
)
for fw in "${UNUSED_FW[@]}"; do
    rm -rf "$QTLIB/${fw}.framework"
done

echo "=== 완료 ==="
du -sh dist/AimGuard.app
echo ""
echo "배포: dist/AimGuard.app 을 다른 Mac으로 복사"
echo "주의: 처음 실행 시 카메라/마이크 권한 허용 필요"
