using System;
using System.Collections.Generic;

static class SteamAvatarRequestsHarness {
    static void Require(bool value, string message) { if (!value) throw new Exception(message); }
    static void Main(string[] args) {
        DateTime start = new DateTime(2024, 1, 1, 0, 0, 0, DateTimeKind.Utc);
        var queue = new SteamAvatarRequests();
        var results = new List<string>();
        if (args[0] == "protocol") {
            ulong id;
            Require(SteamAvatarRequests.TryParseCommand("avatar:76561198000000001", out id) && id == 76561198000000001UL, "valid command");
            Require(!SteamAvatarRequests.TryParseCommand("76561198000000001", out id), "profile command must remain distinct");
            Require(!SteamAvatarRequests.TryParseCommand("avatar:7656119800000000x", out id), "invalid ID");
            Require(!SteamAvatarRequests.TryParseCommand("avatar:00000000000000000", out id), "invalid range");
            Require(!SteamAvatarRequests.TryParseCommand("avatar:76561198000000001\n", out id), "invalid length");
        } else if (args[0] == "dedupe") {
            Require(queue.Enqueue(7) && queue.Enqueue(7), "duplicate queue failure");
            queue.Tick(start, id => "png", (id, image) => results.Add(id + ":" + image));
            Require(results.Count == 1 && results[0] == "7:png", "duplicate result");
        } else if (args[0] == "bounds") {
            for (ulong id = 1; id <= 32; id++) Require(queue.Enqueue(id), "queue filled early");
            Require(!queue.Enqueue(33), "unbounded queue");
            Require(queue.Enqueue(1), "duplicate refused when full");
            queue.Tick(start, id => "png", (id, image) => results.Add(id.ToString()));
            Require(queue.Enqueue(33), "completed request did not free a slot");
        } else if (args[0] == "cadence") {
            for (ulong id = 1; id <= 5; id++) queue.Enqueue(id);
            var firstSeen = new Dictionary<ulong, int>();
            for (int second = 0; second <= 16; second++) {
                int at = second;
                queue.Tick(start.AddSeconds(second), id => { if (!firstSeen.ContainsKey(id)) firstSeen[id] = at; return null; },
                    (id, image) => results.Add(id + ":" + (image ?? "timeout")));
            }
            Require(firstSeen[1] == 0 && firstSeen[2] == 2 && firstSeen[3] == 4 && firstSeen[4] == 6, "cadence");
            Require(firstSeen[5] == 16, "in-flight limit");
            Require(results.Count == 1 && results[0] == "1:timeout", "timeout");
        } else if (args[0] == "retry") {
            queue.Enqueue(1);
            queue.Tick(start, id => null, (id, image) => results.Add(image ?? "unavailable"));
            queue.Tick(start.AddSeconds(14), id => null, (id, image) => results.Add(image ?? "unavailable"));
            Require(results.Count == 0, "premature timeout");
            queue.Tick(start.AddSeconds(15), id => null, (id, image) => results.Add(image ?? "unavailable"));
            Require(results.Count == 1 && results[0] == "unavailable", "missing timeout");
            Require(queue.Enqueue(1), "retry not accepted after timeout");
            queue.Tick(start.AddSeconds(16), id => "new-png", (id, image) => results.Add(image));
            Require(results.Count == 2 && results[1] == "new-png", "retry not completed");
        } else throw new ArgumentException("Unknown scenario");
    }
}
