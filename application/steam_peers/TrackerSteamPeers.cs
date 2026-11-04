// Steam peer detection derived from SteamP2PInfo, Copyright (c) 2022 William Tremblay, MIT.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.IO.Pipes;
using System.Net;
using SteamP2PInfo;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading;
using System.Web.Script.Serialization;
using Steamworks;
class TrackerSteamPeers {
    static JavaScriptSerializer json = new JavaScriptSerializer();
    static HashSet<ulong> registered = new HashSet<ulong>();
    static Dictionary<ulong,DateTime> candidates = new Dictionary<ulong,DateTime>();
    static readonly Queue<ulong> profileRequests = new Queue<ulong>();
    static Regex ids = new Regex(@"\[U:1:(\d+)\]", RegexOptions.Compiled);
    static void Emit(object value) { Console.WriteLine(json.Serialize(value)); Console.Out.Flush(); }
    static void Main(string[] args) {
        Console.OutputEncoding = new UTF8Encoding(false);
        if (args.Length < 2 || args.Length > 4) { Emit(new { status="log_missing" }); return; }
        bool advanced = args.Length >= 3;
        if (advanced) {
            try {
                var pipe = new NamedPipeClientStream(".", args[2], PipeDirection.Out);
                pipe.Connect(15000);
                var commands = new NamedPipeClientStream(".", args[2] + "-cmd", PipeDirection.In);
                commands.Connect(15000);
                Console.SetOut(new StreamWriter(pipe, new UTF8Encoding(false)) { AutoFlush = true });
                Console.SetIn(new StreamReader(commands, Encoding.UTF8));
            } catch (Exception) { return; }
        }
        string pingMode = "admin_required";
        if (advanced) {
            try { ETWPingMonitor.Start(); pingMode = "active"; }
            catch (Exception) { pingMode = "unavailable"; }
        }
        Environment.SetEnvironmentVariable("SteamAppId", "1245620");
        try {
            if (!SteamAPI.Init()) { Emit(new { status="steam_unavailable" }); return; }
            Emit(new { status="waiting_log" });
            var inputThread = new Thread(() => {
                try { string line; while ((line = Console.ReadLine()) != null) {
                    ulong requested;
                    if (UInt64.TryParse(line, out requested)) lock (profileRequests) { profileRequests.Enqueue(requested); }
                } } catch (IOException) { }
            });
            inputThread.IsBackground = true;
            inputThread.Start();
            var parent = Process.GetProcessById(Int32.Parse(args[1]));
            if (args.Length == 4) {
                foreach (string token in args[3].Split(',')) {
                    ulong seed;
                    if (UInt64.TryParse(token, out seed) && seed >= 0x0110000100000000UL) candidates[seed] = DateTime.UtcNow;
                }
            }
            long offset = -1;
            DateTime started = DateTime.Now;
            while (!parent.HasExited && Process.GetProcessesByName("eldenring").Length > 0) {
                lock (profileRequests) {
                    while (profileRequests.Count > 0) {
                        ulong id = profileRequests.Dequeue();
                        var requested = new CSteamID(id);
                        if (requested.BIndividualAccount()) { try { SteamFriends.ActivateGameOverlayToUser("steamid", requested); } catch (Exception) { } }
                    }
                }
                SteamFriends.SendClanChatMessage(new CSteamID(0), "");
                if (!File.Exists(args[0])) { Emit(new { status="waiting_log" }); Thread.Sleep(2000); continue; }
                using (var fs = new FileStream(args[0], FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete)) {
                    if (offset < 0 || offset > fs.Length) offset = fs.Length;
                    fs.Seek(offset, SeekOrigin.Begin);
                    using (var reader = new StreamReader(fs)) {
                        string line;
                        while ((line = reader.ReadLine()) != null) {
                            if (line.IndexOf("eldenring", StringComparison.OrdinalIgnoreCase) < 0) continue;
                            if (line.Contains("LeaveLobby")) { candidates.Clear(); continue; }
                            var match = ids.Match(line); ulong number;
                            if (!match.Success || !ulong.TryParse(match.Groups[1].Value, out number)) continue;
                            ulong id = 0x0110000100000000UL + number;
                            if (line.Contains("BeginAuthSession")) candidates[id] = DateTime.UtcNow;
                            else if (line.Contains("EndAuthSession")) candidates.Remove(id);
                        }
                        offset = fs.Position;
                    }
                }
                var peers = new List<object>();
                foreach (var id in candidates.Keys.ToList()) {
                    var sid = new CSteamID(id);
                    var identity = new SteamNetworkingIdentity(); identity.SetSteamID(sid);
                    SteamNetConnectionInfo_t info; SteamNetConnectionRealTimeStatus_t realtime;
                    bool connected = false;
                    realtime = new SteamNetConnectionRealTimeStatus_t();
                    try {
                        var state = SteamNetworkingMessages.GetSessionConnectionInfo(ref identity, out info, out realtime);
                        connected = state == ESteamNetworkingConnectionState.k_ESteamNetworkingConnectionState_Connected || state == ESteamNetworkingConnectionState.k_ESteamNetworkingConnectionState_Connecting;
                    } catch (Exception) { }
                    P2PSessionState_t legacy = new P2PSessionState_t();
                    bool old = false;
                    try { old = !connected && SteamNetworking.GetP2PSessionState(sid, out legacy) && legacy.m_eP2PSessionError == 0 && (legacy.m_bConnecting != 0 || legacy.m_bConnectionActive != 0); } catch (Exception) { }
                    if (connected || old) {
                        candidates[id] = DateTime.UtcNow;
                        SteamFriends.RequestUserInformation(sid, true);
                        string name = SteamFriends.GetFriendPersonaName(sid);
                        int? ping = connected && realtime.m_nPing >= 0 ? (int?)realtime.m_nPing : null;
                        string address = null;
                        if (old && legacy.m_nRemoteIP != 0) address = new IPAddress(BitConverter.GetBytes(legacy.m_nRemoteIP).Reverse().ToArray()).ToString();
                        if (old && pingMode == "active" && legacy.m_nRemoteIP != 0 && legacy.m_nRemotePort != 0) {
                            byte[] ip = BitConverter.GetBytes(legacy.m_nRemoteIP).Reverse().ToArray();
                            ulong netId = (ulong)legacy.m_nRemotePort << 32 | BitConverter.ToUInt32(ip, 0);
                            if (registered.Add(netId)) ETWPingMonitor.Register(netId);
                            double measured = ETWPingMonitor.GetPing(netId);
                            if (measured >= 0 && measured < 60000) ping = (int)Math.Round(measured);
                        }
                        peers.Add(new { id=id.ToString(), name=String.IsNullOrWhiteSpace(name) ? id.ToString() : name, ping=ping, ip=address, relay=old && legacy.m_bUsingRelay != 0 });
                    } else if ((DateTime.UtcNow - candidates[id]).TotalSeconds > 5) candidates.Remove(id);
                }
                bool logging = File.GetLastWriteTime(args[0]) >= started.AddSeconds(-2);
                Emit(new { status=logging ? "active" : "waiting_log", ping_mode=pingMode, peers=peers });
                Thread.Sleep(1000);
            }
            SteamAPI.Shutdown(); Emit(new { status="game_closed" });
        } catch (Exception) { try { Emit(new { status="helper_error" }); } catch (Exception) { } }
        finally { if (ETWPingMonitor.Running) ETWPingMonitor.Stop(); }
    }
}

