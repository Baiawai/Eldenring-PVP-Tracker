// Bounded on-demand requests for avatars belonging to known historical peers.
// The caller is responsible for authenticating/authorizing the Steam IDs.
using System;
using System.Collections.Generic;
using System.Linq;

public sealed class SteamAvatarRequests {
    public static string MissingImageState(bool loggedOn) {
        return loggedOn ? "unavailable" : "interrupted";
    }
    const int MaxPending = 32;
    const int MaxInFlight = 4;
    static readonly TimeSpan Interval = TimeSpan.FromSeconds(2);
    static readonly TimeSpan Timeout = TimeSpan.FromSeconds(15);
    readonly object gate = new object();
    readonly Queue<ulong> waiting = new Queue<ulong>();
    readonly Dictionary<ulong, DateTime> active = new Dictionary<ulong, DateTime>();
    readonly HashSet<ulong> outstanding = new HashSet<ulong>();
    DateTime nextStart = DateTime.MinValue;

    public static bool TryParseCommand(string line, out ulong id) {
        id = 0;
        if (line == null || line.Length != 24 || !line.StartsWith("avatar:", StringComparison.Ordinal)) return false;
        for (int index = 7; index < line.Length; index++)
            if (line[index] < '0' || line[index] > '9') return false;
        return UInt64.TryParse(line.Substring(7), out id) &&
            id >= 76561197960265729UL && id <= 76561202255233023UL;
    }

    // True also means already queued: duplicate requests share one result.
    public bool Enqueue(ulong id) {
        lock (gate) {
            if (outstanding.Contains(id)) return true;
            if (outstanding.Count >= MaxPending) return false;
            outstanding.Add(id);
            waiting.Enqueue(id);
            return true;
        }
    }

    // Run on the Steam thread. readImage returns a validated PNG encoded as
    // base64 when available, or null while Steam is loading/unavailable.
    public void Tick(DateTime now, Func<ulong, string> readImage, Action<ulong, string> result) {
        List<ulong> due;
        lock (gate) {
            if (waiting.Count > 0 && active.Count < MaxInFlight && now >= nextStart) {
                ulong id = waiting.Dequeue();
                active.Add(id, now + Timeout);
                nextStart = now + Interval;
            }
            due = active.Keys.ToList();
        }
        foreach (ulong id in due) {
            string image = null;
            try { image = readImage(id); } catch (Exception) { }
            bool completed;
            lock (gate) {
                DateTime deadline;
                completed = active.TryGetValue(id, out deadline) && (image != null || now >= deadline);
                if (completed) { active.Remove(id); outstanding.Remove(id); }
            }
            if (completed) result(id, image);
        }
    }
}
