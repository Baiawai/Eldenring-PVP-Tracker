// Exercise the real Steam log reader with synthetic files, without Steam.
using System;
using System.Collections.Generic;
using System.IO;
using System.Text;

internal static class SteamLogTailHarness {
    private const ulong SteamIdBase = 0x0110000100000000UL;
    private static readonly Encoding Utf8 = new UTF8Encoding(false);

    private static string Begin(int id) { return "eldenring BeginAuthSession [U:1:" + id + "]\n"; }
    private static string End(int id) { return "eldenring EndAuthSession [U:1:" + id + "]\n"; }
    private static void Assert(bool condition, string description) {
        if (!condition) throw new Exception(description);
    }

    private static void Poll(SteamLogTail tail, string path, Dictionary<ulong, DateTime> candidates, ref int resets) {
        int localResets = 0;
        tail.Poll(path, line => SteamLogEvents.ProcessLine(line, candidates, DateTime.UtcNow),
                  () => { candidates.Clear(); localResets++; });
        resets += localResets;
    }

    private static void Startup(string path) {
        File.WriteAllText(path, Begin(111) + Begin(222) + End(222) +
                         "anothergame BeginAuthSession [U:1:333]\n" +
                         "eldenring BeginAuthSession [U:1:4294967296]\n", Utf8);
        var tail = new SteamLogTail();
        var candidates = new Dictionary<ulong, DateTime>();
        int resets = 0;
        Poll(tail, path, candidates, ref resets);
        Assert(candidates.Count == 1 && candidates.ContainsKey(SteamIdBase + 111),
               "startup must replay prior game authentication and remove ended sessions");
        File.AppendAllText(path, "eldenring LeaveLobby\n" + Begin(444), Utf8);
        Poll(tail, path, candidates, ref resets);
        Assert(candidates.Count == 1 && candidates.ContainsKey(SteamIdBase + 444),
               "LeaveLobby must clear prior candidates before subsequent authentication");
    }

    private static void Partial(string path) {
        File.WriteAllText(path, Begin(111) + "eldenring BeginAuthSession [U:1:2", Utf8);
        var tail = new SteamLogTail();
        var candidates = new Dictionary<ulong, DateTime>();
        int resets = 0;
        Poll(tail, path, candidates, ref resets);
        Assert(candidates.Count == 1 && candidates.ContainsKey(SteamIdBase + 111),
               "an incomplete final line must not be processed");
        File.AppendAllText(path, "22]\n", Utf8);
        Poll(tail, path, candidates, ref resets);
        Assert(candidates.Count == 2 && candidates.ContainsKey(SteamIdBase + 222),
               "completion of a partial line must be processed exactly once");
        Poll(tail, path, candidates, ref resets);
        Assert(candidates.Count == 2, "polling an unchanged file must not duplicate lines");
    }

    private static void Rotation(string path) {
        File.WriteAllText(path, Begin(111), Utf8);
        var tail = new SteamLogTail();
        var candidates = new Dictionary<ulong, DateTime>();
        int resets = 0;
        Poll(tail, path, candidates, ref resets);
        File.Move(path, path + ".old");
        File.WriteAllText(path, Begin(222), Utf8); // Same length, different file.
        Poll(tail, path, candidates, ref resets);
        Assert(resets > 0 && candidates.Count == 1 && candidates.ContainsKey(SteamIdBase + 222),
               "replacement by a same-size log must reset prior candidates");
    }

    private static void Truncation(string path) {
        File.WriteAllText(path, Begin(111) + Begin(222) + Begin(333), Utf8);
        var tail = new SteamLogTail();
        var candidates = new Dictionary<ulong, DateTime>();
        int resets = 0;
        Poll(tail, path, candidates, ref resets);
        File.WriteAllText(path, Begin(444), Utf8);
        Poll(tail, path, candidates, ref resets);
        Assert(resets > 0 && candidates.Count == 1 && candidates.ContainsKey(SteamIdBase + 444),
               "truncation must reset previous candidates and replay the new log");
    }

    private static void LimitedHistory(string path) {
        var content = new StringBuilder(Begin(111));
        for (int i = 0; i < 30; i++) content.Append("irrelevant historical entry\n");
        content.Append(Begin(222));
        File.WriteAllText(path, content.ToString(), Utf8);
        var tail = new SteamLogTail(128);
        var candidates = new Dictionary<ulong, DateTime>();
        int resets = 0;
        Poll(tail, path, candidates, ref resets);
        Assert(!candidates.ContainsKey(SteamIdBase + 111) && candidates.ContainsKey(SteamIdBase + 222),
               "bounded initial replay must read the recent complete lines, not the entire history");
    }

    private static void Missing(string path) {
        var tail = new SteamLogTail();
        var candidates = new Dictionary<ulong, DateTime>();
        int resets = 0;
        bool found = tail.Poll(path, line => SteamLogEvents.ProcessLine(line, candidates, DateTime.UtcNow),
                               () => { candidates.Clear(); });
        Assert(!found && candidates.Count == 0, "missing log must remain unavailable");
        File.WriteAllText(path, Begin(111), Utf8);
        Poll(tail, path, candidates, ref resets);
        Assert(candidates.Count == 1 && candidates.ContainsKey(SteamIdBase + 111),
               "a log created after startup must still replay existing complete lines");
    }

    public static int Main(string[] args) {
        string directory = Path.Combine(Path.GetTempPath(), "tracker-steam-log-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        try {
            string path = Path.Combine(directory, "ipc_SteamClient.log");
            switch (args[0]) {
                case "startup": Startup(path); break;
                case "partial": Partial(path); break;
                case "rotation": Rotation(path); break;
                case "truncation": Truncation(path); break;
                case "history": LimitedHistory(path); break;
                case "missing": Missing(path); break;
                default: throw new ArgumentException("Unknown scenario");
            }
            return 0;
        } catch (Exception error) {
            Console.Error.WriteLine(error);
            return 1;
        } finally {
            Directory.Delete(directory, true);
        }
    }
}
