using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEngine;

[Serializable]
public class HeroImportCheck
{
    public string name;
    public bool passed;
    public string expected;
    public string actual;
}

[Serializable]
public class HeroImportClip
{
    public string name;
    public float lengthSeconds;
    public int curves;
}

[Serializable]
public class HeroImportTexture
{
    public string name;
    public int width;
    public int height;
    public string source;
}

[Serializable]
public class HeroImportBounds
{
    public float sizeX;
    public float sizeY;
    public float sizeZ;
    public float minY;
}

[Serializable]
public class HeroImportModelFacts
{
    public string importedAssetPath;
    public int boneCount;
    public string[] bones;
    public string[] missingCapeBones;
    public string[] blendShapes;
    public HeroImportClip[] clips;
    public string[] materials;
    public HeroImportTexture[] textures;
    public int triangleCount;
    public float heightMeters;
    public HeroImportBounds bounds;
}

[Serializable]
public class HeroImportImporterSettings
{
    public string animationType;
    public bool importAnimation;
    public bool importBlendShapes;
    public bool importMaterials;
    public bool useFileScale;
    public float globalScale;
    public bool scaleRetry;
}

[Serializable]
public class HeroImportReport
{
    public string schema;
    public string generatedUtc;
    public string unityVersion;
    public string projectPath;
    public string sourceFbx;
    public long sourceFbxBytes;
    public string sourceFbxSha256;
    public string importedAssetPath;
    public HeroImportImporterSettings importer;
    public bool passed;
    public HeroImportCheck[] checks;
    public HeroImportModelFacts model;
    public string[] notes;
    public string[] errors;
}

public static class HeroImportProof
{
    private const string TempAssetFolder = "Assets/Editor/HeroImportProofTemp";
    private const string FbxFileName = "wayfarer.fbx";
    private const int ExpectedBoneCount = 23;
    private static readonly string[] ExpectedCapeBones = { "cape_a", "cape_b", "cape_c" };
    private static readonly string[] ExpectedClipNames = { "idle", "run", "reach" };
    private static readonly string[] ExpectedMaterialNames =
        { "Wayfarer_Cloth", "Wayfarer_Leather", "Wayfarer_Skin", "Wayfarer_Accent" };
    private static readonly string[] ExpectedTextureNames = { "wayfarer_atlas", "wayfarer_normal" };

    private static readonly List<HeroImportCheck> s_checks = new List<HeroImportCheck>();
    private static readonly List<string> s_notes = new List<string>();
    private static readonly List<string> s_errors = new List<string>();
    private static readonly List<string> s_bones = new List<string>();
    private static readonly List<string> s_blendShapes = new List<string>();
    private static readonly List<HeroImportClip> s_clips = new List<HeroImportClip>();
    private static readonly List<string> s_materials = new List<string>();
    private static readonly List<HeroImportTexture> s_textures = new List<HeroImportTexture>();
    private static int s_triangles;
    private static float s_height;
    private static Vector3 s_min;
    private static Vector3 s_max;
    private static float s_globalScale = 1f;
    private static bool s_scaleRetry;

    [MenuItem("LeftBehind/Hero Import Proof")]
    public static void Run()
    {
        var reportPath = FirstNonEmpty(Environment.GetEnvironmentVariable("GYPSY_HERO_REPORT"), GetArgument("-heroReport"));
        if (string.IsNullOrEmpty(reportPath))
        {
            reportPath = Path.Combine(RepoRoot(), "artifacts", "unity-hero-import", "hero-import-report.json");
        }
        reportPath = Path.GetFullPath(reportPath);
        var sourceArg = FirstNonEmpty(Environment.GetEnvironmentVariable("GYPSY_HERO_FBX"), GetArgument("-heroFbx"));
        var sourceFbx = string.IsNullOrEmpty(sourceArg)
            ? Path.Combine(RepoRoot(), "assets", "hero", "wayfarer.fbx")
            : Path.GetFullPath(sourceArg);
        var projectPath = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
        string sourceSha = "";
        long sourceBytes = 0;
        var report = new HeroImportReport
        {
            schema = "gypsy.unity.hero-import/v1",
            generatedUtc = DateTime.UtcNow.ToString("o", CultureInfo.InvariantCulture),
            unityVersion = Application.unityVersion,
            projectPath = projectPath,
            sourceFbx = sourceFbx,
            importedAssetPath = TempAssetFolder + "/" + FbxFileName,
        };
        Directory.CreateDirectory(Path.GetDirectoryName(reportPath));

        try
        {
            Note("Unity " + Application.unityVersion + " project=" + projectPath);
            var exists = File.Exists(sourceFbx);
            AddCheck("source fbx exists", exists, "file at " + sourceFbx, exists ? "exists" : "missing");
            if (!exists)
            {
                throw new FileNotFoundException("source FBX is missing", sourceFbx);
            }
            var info = new FileInfo(sourceFbx);
            sourceBytes = info.Length;
            sourceSha = Sha256(sourceFbx);
            AddCheck("source fbx is non-empty", info.Length > 100000, "> 100000 bytes",
                info.Length.ToString(CultureInfo.InvariantCulture) + " bytes");
            Note("source bytes=" + sourceBytes + " sha256=" + sourceSha);

            CleanupTemp();
            var tempAbs = Path.Combine(Application.dataPath, "Editor", "HeroImportProofTemp");
            Directory.CreateDirectory(tempAbs);
            File.Copy(sourceFbx, Path.Combine(tempAbs, FbxFileName), true);
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            var assetPath = TempAssetFolder + "/" + FbxFileName;
            AssetDatabase.ImportAsset(assetPath,
                ImportAssetOptions.ForceUpdate | ImportAssetOptions.ForceSynchronousImport);

            var importer = AssetImporter.GetAtPath(assetPath) as ModelImporter;
            AddCheck("model importer available", importer != null, "ModelImporter", importer == null ? "null" : "ok");
            if (importer == null)
            {
                throw new InvalidOperationException("no ModelImporter found at " + assetPath);
            }
            importer.importAnimation = true;
            importer.animationType = ModelImporterAnimationType.Generic;
            importer.importBlendShapes = true;
            importer.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
            importer.importCameras = false;
            importer.importLights = false;
            importer.importVisibility = false;
            importer.useFileScale = false;
            importer.globalScale = 1f;
            importer.SaveAndReimport();
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);

            MeasureModel(assetPath, importer);
            if (s_height < 1.7f || s_height > 2.1f)
            {
                var factor = 1.9f / Mathf.Max(0.001f, s_height);
                var corrected = ClosestPowerOfTen(factor);
                Note("imported height " + Format(s_height) + " m is outside 1.7-2.1 m; retrying with globalScale=" +
                     Format(corrected));
                importer.globalScale = corrected;
                importer.SaveAndReimport();
                AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
                s_globalScale = corrected;
                s_scaleRetry = true;
                MeasureModel(assetPath, importer);
            }

            var missingCape = ExpectedCapeBones.Where(bone => !s_bones.Contains(bone)).ToArray();
            AddCheck("bone count is 23", s_bones.Count == ExpectedBoneCount,
                ExpectedBoneCount.ToString(CultureInfo.InvariantCulture), s_bones.Count + " bones");
            AddCheck("cape bone chain present", missingCape.Length == 0, "cape_a, cape_b, cape_c",
                missingCape.Length == 0 ? "present" : "missing " + string.Join(",", missingCape));
            AddCheck("Smile blend shape present",
                s_blendShapes.Any(shape => shape.IndexOf("Smile", StringComparison.OrdinalIgnoreCase) >= 0),
                "Smile", s_blendShapes.Count == 0 ? "none" : string.Join(",", s_blendShapes));

            foreach (var expectedClip in ExpectedClipNames)
            {
                var clip = s_clips.FirstOrDefault(item =>
                    item.name.IndexOf(expectedClip, StringComparison.OrdinalIgnoreCase) >= 0);
                AddCheck("animation clip " + expectedClip, clip != null, expectedClip + " clip",
                    clip == null
                        ? "missing (found " + string.Join(",", s_clips.Select(item => item.name)) + ")"
                        : clip.name + " length=" + Format(clip.lengthSeconds) + "s curves=" + clip.curves);
            }

            var missingMaterials = ExpectedMaterialNames
                .Where(expected => !s_materials.Any(name =>
                    name.IndexOf(expected, StringComparison.OrdinalIgnoreCase) >= 0)).ToArray();
            AddCheck("materials imported", missingMaterials.Length == 0, string.Join(",", ExpectedMaterialNames),
                s_materials.Count == 0 ? "none" : string.Join(",", s_materials));

            var textureNames = s_textures.Select(texture => texture.name.ToLowerInvariant()).ToList();
            AddCheck("atlas texture imported", textureNames.Any(name => name.Contains("wayfarer_atlas")),
                "wayfarer_atlas", textureNames.Count == 0 ? "none" : string.Join(",", s_textures.Select(t => t.name)));
            AddCheck("normal map imported", textureNames.Any(name => name.Contains("wayfarer_normal")),
                "wayfarer_normal", textureNames.Count == 0 ? "none" : string.Join(",", s_textures.Select(t => t.name)));
            var expectedTextureFacts = s_textures.Where(texture =>
                ExpectedTextureNames.Any(expected => texture.name.IndexOf(expected, StringComparison.OrdinalIgnoreCase) >= 0)).ToArray();
            AddCheck("imported texture maps are at least 256px",
                expectedTextureFacts.Length > 0 && expectedTextureFacts.All(texture => texture.width >= 256 && texture.height >= 256),
                ">=256x256",
                expectedTextureFacts.Length == 0
                    ? "no expected textures"
                    : string.Join(",", expectedTextureFacts.Select(t => t.name + "=" + t.width + "x" + t.height)));
            Note("roughmetal map is glTF-only; the FBX material model carries the atlas and normal map.");

            AddCheck("height is human scale in metres", s_height >= 1.7f && s_height <= 2.1f,
                "1.70-2.10 m", Format(s_height) + " m");
            AddCheck("feet rest near the origin", Mathf.Abs(s_min.y) <= 0.15f, "|minY| <= 0.15 m",
                "minY=" + Format(s_min.y) + " m");
            AddCheck("mesh has triangle geometry", s_triangles >= 500, ">=500 triangles",
                s_triangles.ToString(CultureInfo.InvariantCulture) + " triangles");
        }
        catch (Exception exception)
        {
            s_errors.Add(exception.ToString());
            Debug.LogError("[HeroImportProof] " + exception);
        }
        finally
        {
            try
            {
                CleanupTemp();
            }
            catch (Exception cleanupException)
            {
                s_notes.Add("cleanup warning: " + cleanupException.Message);
            }
            var passed = s_checks.All(check => check.passed) && s_errors.Count == 0;
            report.sourceFbxBytes = sourceBytes;
            report.sourceFbxSha256 = sourceSha;
            report.importer = new HeroImportImporterSettings
            {
                animationType = "Generic",
                importAnimation = true,
                importBlendShapes = true,
                importMaterials = true,
                useFileScale = false,
                globalScale = s_globalScale,
                scaleRetry = s_scaleRetry,
            };
            report.passed = passed;
            report.checks = s_checks.ToArray();
            report.model = new HeroImportModelFacts
            {
                importedAssetPath = TempAssetFolder + "/" + FbxFileName,
                boneCount = s_bones.Count,
                bones = s_bones.ToArray(),
                missingCapeBones = ExpectedCapeBones.Where(bone => !s_bones.Contains(bone)).ToArray(),
                blendShapes = s_blendShapes.ToArray(),
                clips = s_clips.ToArray(),
                materials = s_materials.ToArray(),
                textures = s_textures.ToArray(),
                triangleCount = s_triangles,
                heightMeters = s_height,
                bounds = new HeroImportBounds
                {
                    sizeX = s_max.x - s_min.x,
                    sizeY = s_max.y - s_min.y,
                    sizeZ = s_max.z - s_min.z,
                    minY = s_min.y,
                },
            };
            report.notes = s_notes.ToArray();
            report.errors = s_errors.ToArray();
            try
            {
                File.WriteAllText(reportPath, JsonUtility.ToJson(report, true), new UTF8Encoding(false));
                Note("report written to " + reportPath);
            }
            catch (Exception writeException)
            {
                Debug.LogError("[HeroImportProof] report write failed: " + writeException);
                passed = false;
            }
            var summary = "bones=" + s_bones.Count + " clips=" + string.Join(",", s_clips.Select(clip => clip.name)) +
                          " blendShapes=" + string.Join(",", s_blendShapes) +
                          " materials=" + s_materials.Count + " textures=" + s_textures.Count +
                          " height=" + Format(s_height) + "m";
            if (passed)
            {
                Debug.Log("UNITY_HERO_IMPORT_OK " + summary);
            }
            else
            {
                Debug.Log("UNITY_HERO_IMPORT_FAIL " + summary + " failures=" +
                          string.Join("; ", s_checks.Where(check => !check.passed).Select(check => check.name)) +
                          (s_errors.Count == 0 ? "" : " errors=" + s_errors[0].Split('\n')[0]));
            }
            EditorApplication.Exit(passed ? 0 : 1);
        }
    }

    private static void MeasureModel(string assetPath, ModelImporter importer)
    {
        s_bones.Clear();
        s_blendShapes.Clear();
        s_clips.Clear();
        s_materials.Clear();
        s_textures.Clear();
        s_triangles = 0;
        s_height = 0f;
        s_min = Vector3.zero;
        s_max = Vector3.zero;

        var assets = AssetDatabase.LoadAllAssetsAtPath(assetPath);
        foreach (var clip in assets.OfType<AnimationClip>())
        {
            if (clip == null || s_clips.Any(item => item.name == clip.name))
            {
                continue;
            }
            var curves = AnimationUtility.GetCurveBindings(clip).Length +
                         AnimationUtility.GetObjectReferenceCurveBindings(clip).Length;
            s_clips.Add(new HeroImportClip { name = clip.name, lengthSeconds = clip.length, curves = curves });
        }
        if (importer != null)
        {
            foreach (var clip in importer.clipAnimations)
            {
                if (!s_clips.Any(item => item.name == clip.name))
                {
                    s_clips.Add(new HeroImportClip { name = clip.name, lengthSeconds = 0f, curves = 0 });
                }
            }
        }
        foreach (var material in assets.OfType<Material>())
        {
            if (material != null && !s_materials.Contains(material.name))
            {
                s_materials.Add(material.name);
            }
        }
        foreach (var texture in assets.OfType<Texture2D>())
        {
            if (texture != null && !s_textures.Any(item => item.name == texture.name))
            {
                s_textures.Add(new HeroImportTexture
                {
                    name = texture.name,
                    width = texture.width,
                    height = texture.height,
                    source = "sub-asset",
                });
            }
        }

        var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
        if (prefab == null)
        {
            throw new InvalidOperationException("imported model prefab is missing at " + assetPath);
        }
        var instance = UnityEngine.Object.Instantiate(prefab);
        try
        {
            var bounds = new Bounds();
            var first = true;
            foreach (var renderer in instance.GetComponentsInChildren<SkinnedMeshRenderer>(true))
            {
                var mesh = renderer.sharedMesh;
                if (mesh == null)
                {
                    continue;
                }
                s_triangles += mesh.triangles.Length / 3;
                for (var index = 0; index < mesh.blendShapeCount; index++)
                {
                    var shape = mesh.GetBlendShapeName(index);
                    if (!s_blendShapes.Contains(shape))
                    {
                        s_blendShapes.Add(shape);
                    }
                }
                foreach (var bone in renderer.bones)
                {
                    if (bone != null && !s_bones.Contains(bone.name))
                    {
                        s_bones.Add(bone.name);
                    }
                }
                foreach (var material in renderer.sharedMaterials)
                {
                    if (material != null && !s_materials.Contains(material.name))
                    {
                        s_materials.Add(material.name);
                    }
                }
                var matrix = renderer.transform.localToWorldMatrix;
                var meshBounds = mesh.bounds;
                for (var corner = 0; corner < 8; corner++)
                {
                    var point = new Vector3(
                        meshBounds.center.x + (corner % 2 == 0 ? -1f : 1f) * meshBounds.extents.x,
                        meshBounds.center.y + ((corner / 2) % 2 == 0 ? -1f : 1f) * meshBounds.extents.y,
                        meshBounds.center.z + ((corner / 4) % 2 == 0 ? -1f : 1f) * meshBounds.extents.z);
                    var world = matrix.MultiplyPoint3x4(point);
                    if (first)
                    {
                        bounds = new Bounds(world, Vector3.zero);
                        first = false;
                    }
                    else
                    {
                        bounds.Encapsulate(world);
                    }
                }
            }
            if (first)
            {
                throw new InvalidOperationException("no SkinnedMeshRenderer with mesh found in the imported model");
            }
            s_height = bounds.size.y;
            s_min = bounds.min;
            s_max = bounds.max;
        }
        finally
        {
            UnityEngine.Object.DestroyImmediate(instance);
        }

        if (!s_textures.Any(item => item.name.IndexOf("wayfarer_atlas", StringComparison.OrdinalIgnoreCase) >= 0) ||
            !s_textures.Any(item => item.name.IndexOf("wayfarer_normal", StringComparison.OrdinalIgnoreCase) >= 0))
        {
            ExtractEmbeddedTextures(importer);
        }
    }

    private static void ExtractEmbeddedTextures(ModelImporter importer)
    {
        if (importer == null)
        {
            return;
        }
        var extractRel = TempAssetFolder + "/ExtractedTextures";
        var extractAbs = Path.Combine(Application.dataPath, "Editor", "HeroImportProofTemp", "ExtractedTextures");
        Directory.CreateDirectory(extractAbs);
        try
        {
            importer.ExtractTextures(extractAbs);
        }
        catch (Exception exception)
        {
            s_notes.Add("ExtractTextures failed: " + exception.Message);
            return;
        }
        AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        if (!AssetDatabase.IsValidFolder(extractRel))
        {
            s_notes.Add("ExtractTextures produced no folder at " + extractRel);
            return;
        }
        foreach (var guid in AssetDatabase.FindAssets("t:Texture2D", new[] { extractRel }))
        {
            var path = AssetDatabase.GUIDToAssetPath(guid);
            var texture = AssetDatabase.LoadAssetAtPath<Texture2D>(path);
            if (texture != null && !s_textures.Any(item => item.name == texture.name))
            {
                s_textures.Add(new HeroImportTexture
                {
                    name = texture.name,
                    width = texture.width,
                    height = texture.height,
                    source = "extracted",
                });
            }
        }
        s_notes.Add("textures extracted from the embedded FBX media: " + s_textures.Count);
    }

    private static void AddCheck(string name, bool passed, string expected, string actual)
    {
        s_checks.Add(new HeroImportCheck { name = name, passed = passed, expected = expected, actual = actual });
        if (passed)
        {
            Debug.Log("[HeroImportProof] PASS " + name + " (" + actual + ")");
        }
        else
        {
            Debug.Log("[HeroImportProof] FAIL " + name + " expected=" + expected + " actual=" + actual);
        }
    }

    private static void Note(string message)
    {
        s_notes.Add(message);
        Debug.Log("[HeroImportProof] " + message);
    }

    private static string Sha256(string path)
    {
        using (var stream = File.OpenRead(path))
        using (var sha = SHA256.Create())
        {
            var hash = sha.ComputeHash(stream);
            var builder = new StringBuilder(hash.Length * 2);
            foreach (var value in hash)
            {
                builder.Append(value.ToString("x2", CultureInfo.InvariantCulture));
            }
            return builder.ToString();
        }
    }

    private static string RepoRoot()
    {
        return Path.GetFullPath(Path.Combine(Application.dataPath, "..", "..", ".."));
    }

    private static string FirstNonEmpty(string first, string second)
    {
        return string.IsNullOrEmpty(first) ? second : first;
    }

    private static string GetArgument(string name)
    {
        var arguments = Environment.GetCommandLineArgs();
        for (var index = 0; index < arguments.Length - 1; index++)
        {
            if (string.Equals(arguments[index], name, StringComparison.OrdinalIgnoreCase))
            {
                return arguments[index + 1];
            }
        }
        return null;
    }

    private static void CleanupTemp()
    {
        if (AssetDatabase.IsValidFolder(TempAssetFolder))
        {
            AssetDatabase.DeleteAsset(TempAssetFolder);
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        }
        var tempAbs = Path.Combine(Application.dataPath, "Editor", "HeroImportProofTemp");
        if (Directory.Exists(tempAbs))
        {
            Directory.Delete(tempAbs, true);
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        }
    }

    private static float ClosestPowerOfTen(float value)
    {
        float[] candidates = { 0.01f, 0.1f, 1f, 10f, 100f };
        return candidates.OrderBy(candidate => Mathf.Abs(Mathf.Log10(candidate / value))).First();
    }

    private static string Format(float value)
    {
        return value.ToString("0.000", CultureInfo.InvariantCulture);
    }
}
