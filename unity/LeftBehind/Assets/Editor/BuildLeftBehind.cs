using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEditor.SceneManagement;
using UnityEngine;

public static class BuildLeftBehind
{
    [MenuItem("LeftBehind/Build Windows")]
    public static void Build()
    {
        PlayerSettings.productName = "LeftBehind";
        PlayerSettings.companyName = "C7-IMI";
        Directory.CreateDirectory("Assets/Scenes");
        var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
        var host = new GameObject("LeftBehind");
        host.AddComponent<LeftBehindDemo>();
        var scenePath = "Assets/Scenes/Main.unity";
        EditorSceneManager.SaveScene(scene, scenePath);
        EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(scenePath, true) };
        Directory.CreateDirectory("Build");
        var options = new BuildPlayerOptions
        {
            scenes = new[] { scenePath },
            locationPathName = "Build/LeftBehind.exe",
            target = BuildTarget.StandaloneWindows64,
            options = BuildOptions.None
        };
        var report = BuildPipeline.BuildPlayer(options);
        Debug.Log("LEFTBEHIND_BUILD " + report.summary.result + " bytes=" + report.summary.totalSize);
        EditorApplication.Exit(report.summary.result == BuildResult.Succeeded ? 0 : 1);
    }
}
