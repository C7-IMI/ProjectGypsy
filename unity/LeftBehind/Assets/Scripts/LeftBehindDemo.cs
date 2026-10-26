using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

public class LeftBehindDemo : MonoBehaviour
{
    private readonly List<GameObject> crystals = new List<GameObject>();
    private CharacterController controller;
    private Transform playerTransform;
    private Camera cam;
    private int collected;
    private int frames;
    private bool demo;
    private string capturePath;
    private float vy;

    private const float Speed = 6f;
    private const int MaxDemoFrames = 900;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    private static void EnsureHost()
    {
        if (FindObjectOfType<LeftBehindDemo>() == null)
        {
            var host = new GameObject("LeftBehind");
            host.AddComponent<LeftBehindDemo>();
        }
    }

    private void Start()
    {
        demo = Array.Exists(Environment.GetCommandLineArgs(), value => value == "--demo");
        capturePath = GetArg("--capture=");
        BuildWorld();
        Debug.Log("LEFTBEHIND_START demo=" + demo + " crystals=" + crystals.Count);
        if (demo) StartCoroutine(RunDemo());
    }

    private static string GetArg(string prefix)
    {
        foreach (var value in Environment.GetCommandLineArgs())
        {
            if (value.StartsWith(prefix, StringComparison.Ordinal)) return value.Substring(prefix.Length);
        }
        return null;
    }

    private Material Mat(Color color, float emission = 0f)
    {
        var shader = Shader.Find("Standard");
        var material = new Material(shader != null ? shader : Shader.Find("Legacy Shaders/Diffuse"));
        material.color = color;
        if (emission > 0f)
        {
            material.EnableKeyword("_EMISSION");
            material.SetColor("_EmissionColor", color * emission);
        }
        return material;
    }

    private void BuildWorld()
    {
        RenderSettings.ambientLight = new Color(0.11f, 0.15f, 0.20f);
        RenderSettings.fog = true;
        RenderSettings.fogColor = new Color(0.03f, 0.05f, 0.08f);
        RenderSettings.fogMode = FogMode.ExponentialSquared;
        RenderSettings.fogDensity = 0.018f;

        var floor = GameObject.CreatePrimitive(PrimitiveType.Cube);
        floor.name = "Floor";
        floor.transform.position = new Vector3(0f, -0.5f, 0f);
        floor.transform.localScale = new Vector3(30f, 1f, 30f);
        floor.GetComponent<Renderer>().sharedMaterial = Mat(new Color(0.08f, 0.12f, 0.16f));

        var platformColor = new Color(0.13f, 0.22f, 0.27f);
        AddPlatform(new Vector3(-5f, 0.25f, -4f), new Vector3(4f, 0.5f, 4f), platformColor);
        AddPlatform(new Vector3(5f, 0.5f, -3f), new Vector3(3f, 1f, 3f), platformColor);
        AddPlatform(new Vector3(-2f, 0.75f, 5f), new Vector3(3f, 1.5f, 3f), platformColor);
        AddPlatform(new Vector3(4f, 1.0f, 5f), new Vector3(2f, 2f, 2f), platformColor);

        var player = GameObject.CreatePrimitive(PrimitiveType.Capsule);
        player.name = "Player";
        player.transform.position = new Vector3(0f, 1.05f, 0f);
        player.GetComponent<Renderer>().sharedMaterial = Mat(new Color(0.18f, 0.48f, 0.82f));
        playerTransform = player.transform;
        controller = player.AddComponent<CharacterController>();
        controller.height = 2f;
        controller.radius = 0.5f;
        controller.center = new Vector3(0f, 0f, 0f);

        var crystalColor = new Color(0.16f, 0.86f, 0.76f);
        AddCrystal("Crystal_A", new Vector3(3f, 1.2f, 0f), crystalColor);
        AddCrystal("Crystal_B", new Vector3(-3f, 1.2f, 2f), crystalColor);
        AddCrystal("Crystal_C", new Vector3(0f, 1.2f, -3f), crystalColor);

        var cameraObject = new GameObject("Main Camera");
        cameraObject.tag = "MainCamera";
        cam = cameraObject.AddComponent<Camera>();
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = new Color(0.02f, 0.03f, 0.05f);
        cam.fieldOfView = 55f;
        cameraObject.transform.position = new Vector3(0f, 8f, -10f);

        var lightObject = new GameObject("Key Light");
        var light = lightObject.AddComponent<Light>();
        light.type = LightType.Directional;
        light.color = new Color(0.82f, 0.91f, 1f);
        light.intensity = 1.1f;
        lightObject.transform.rotation = Quaternion.Euler(48f, -28f, 0f);
    }

    private void AddPlatform(Vector3 position, Vector3 scale, Color color)
    {
        var platform = GameObject.CreatePrimitive(PrimitiveType.Cube);
        platform.name = "Platform";
        platform.transform.position = position;
        platform.transform.localScale = scale;
        platform.GetComponent<Renderer>().sharedMaterial = Mat(color);
    }

    private void AddCrystal(string name, Vector3 position, Color color)
    {
        var crystal = GameObject.CreatePrimitive(PrimitiveType.Cube);
        crystal.name = name;
        crystal.transform.position = position;
        crystal.transform.localScale = new Vector3(0.45f, 0.9f, 0.45f);
        crystal.transform.rotation = Quaternion.Euler(0f, 45f, 45f);
        crystal.GetComponent<Renderer>().sharedMaterial = Mat(color, 1.8f);
        crystals.Add(crystal);
    }

    private void Update()
    {
        if (demo || controller == null) return;
        float horizontal = 0f;
        float vertical = 0f;
        if (Input.GetKey(KeyCode.A) || Input.GetKey(KeyCode.LeftArrow)) horizontal = -1f;
        if (Input.GetKey(KeyCode.D) || Input.GetKey(KeyCode.RightArrow)) horizontal = 1f;
        if (Input.GetKey(KeyCode.W) || Input.GetKey(KeyCode.UpArrow)) vertical = 1f;
        if (Input.GetKey(KeyCode.S) || Input.GetKey(KeyCode.DownArrow)) vertical = -1f;
        MovePlayer(new Vector3(horizontal, 0f, vertical), Time.deltaTime);
        CollectNearby();
    }

    private void MovePlayer(Vector3 direction, float deltaTime)
    {
        if (controller.isGrounded && vy < 0f) vy = -2f;
        vy -= 9.81f * deltaTime;
        var motion = direction.normalized * Speed * deltaTime + Vector3.up * vy * deltaTime;
        controller.Move(motion);
    }

    private void CollectNearby()
    {
        for (int index = crystals.Count - 1; index >= 0; index--)
        {
            var crystal = crystals[index];
            if (crystal == null) { crystals.RemoveAt(index); continue; }
            var delta = crystal.transform.position - playerTransform.position;
            delta.y = 0f;
            if (delta.magnitude < 1.15f)
            {
                crystals.RemoveAt(index);
                Destroy(crystal);
                collected++;
            }
        }
    }

    private GameObject NearestCrystal()
    {
        GameObject best = null;
        float bestDistance = float.MaxValue;
        foreach (var crystal in crystals)
        {
            if (crystal == null) continue;
            var delta = crystal.transform.position - playerTransform.position;
            delta.y = 0f;
            if (delta.magnitude < bestDistance)
            {
                bestDistance = delta.magnitude;
                best = crystal;
            }
        }
        return best;
    }

    private IEnumerator RunDemo()
    {
        while (collected < 3 && frames < MaxDemoFrames)
        {
            frames++;
            if (frames % 100 == 0) Debug.Log("LEFTBEHIND_FRAME " + frames + " pos=" + playerTransform.position + " crystals=" + crystals.Count);
            var target = NearestCrystal();
            if (target != null)
            {
                var direction = target.transform.position - playerTransform.position;
                direction.y = 0f;
                MovePlayer(direction, Time.fixedDeltaTime);
            }
            CollectNearby();
            yield return new WaitForFixedUpdate();
        }

        if (collected == 3)
        {
            Debug.Log("GYPSY_DEMO_OK collected=3 frames=" + frames);
            if (!string.IsNullOrEmpty(capturePath))
            {
                var folder = Path.GetDirectoryName(capturePath);
                if (!string.IsNullOrEmpty(folder)) Directory.CreateDirectory(folder);
                yield return new WaitForEndOfFrame();
                ScreenCapture.CaptureScreenshot(capturePath);
                yield return new WaitForSeconds(1.0f);
            }
            yield return new WaitForSeconds(0.2f);
            Application.Quit(0);
            yield return null;
            System.Environment.Exit(0);
        }
        else
        {
            Debug.Log("GYPSY_DEMO_FAIL collected=" + collected + " frames=" + frames);
            Application.Quit(1);
            yield return null;
            System.Environment.Exit(1);
        }
    }

    private void LateUpdate()
    {
        if (cam == null) return;
        cam.transform.position = playerTransform.position + new Vector3(0f, 8f, -10f);
        cam.transform.LookAt(playerTransform.position + Vector3.up * 1.0f);
    }
}
