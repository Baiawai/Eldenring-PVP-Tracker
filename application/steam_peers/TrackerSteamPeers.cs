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
using System.Threading;
using System.Web.Script.Serialization;
using System.Drawing;
using System.Drawing.Imaging;
using System.Runtime.InteropServices;
using Steamworks;
class TrackerSteamPeers {
    static JavaScriptSerializer json = new JavaScriptSerializer();
    static HashSet<ulong> registered = new HashSet<ulong>();
    static Dictionary<ulong,DateTime> candidates = new Dictionary<ulong,DateTime>();
    static readonly Queue<ulong> profileRequests = new Queue<ulong>();
    static readonly SteamAvatarRequests historicalAvatars = new SteamAvatarRequests();
    static readonly Queue<ulong> rejectedAvatars = new Queue<ulong>();
    class AvatarState {
        public DateTime nextRequest = DateTime.MinValue;
        public DateTime nextCheck = DateTime.MinValue;
        public DateTime nextSend = DateTime.MinValue;
        public int lastHandle;
    }
    static readonly Dictionary<ulong, AvatarState> avatars = new Dictionary<ulong, AvatarState>();
    static string AvatarUpdate(CSteamID sid, ulong id, DateTime now, bool force = false) {
        AvatarState state;
        if (!avatars.TryGetValue(id, out state)) {
            if (avatars.Count >= 128) {
                ulong oldest = avatars.OrderBy(entry => entry.Value.nextRequest).First().Key;
                avatars.Remove(oldest);
            }
            state = new AvatarState(); avatars[id] = state;
        }
        try {
            if (now >= state.nextRequest) {
                state.nextRequest = now.AddMinutes(5);
                SteamFriends.RequestUserInformation(sid, false);
            }
            if (!force && now < state.nextCheck) return null;
            int handle = SteamFriends.GetMediumFriendAvatar(sid);
            if (!force) state.nextCheck = now.AddSeconds(handle < 0 ? 3 : 60);
            if (handle <= 0 || (!force && handle == state.lastHandle && now < state.nextSend)) return null;
            uint width, height;
            if (!SteamUtils.GetImageSize(handle, out width, out height) || width == 0 || height == 0 || width > 128 || height > 128) return null;
            byte[] rgba = new byte[checked((int)(width * height * 4))];
            if (!SteamUtils.GetImageRGBA(handle, rgba, rgba.Length)) return null;
            // Steam supplies RGBA and GDI+ expects BGRA.
            for (int i = 0; i < rgba.Length; i += 4) { byte red = rgba[i]; rgba[i] = rgba[i + 2]; rgba[i + 2] = red; }
            using (var image = new Bitmap((int)width, (int)height, PixelFormat.Format32bppArgb)) {
                BitmapData bits = image.LockBits(new Rectangle(0, 0, (int)width, (int)height), ImageLockMode.WriteOnly, PixelFormat.Format32bppArgb);
                try { for (int y = 0; y < (int)height; y++) Marshal.Copy(rgba, y * (int)width * 4, IntPtr.Add(bits.Scan0, y * bits.Stride), (int)width * 4); }
                finally { image.UnlockBits(bits); }
                using (var stream = new MemoryStream()) {
                    image.Save(stream, ImageFormat.Png);
                    // Historical requests must not consume a live peer's
                    // pending avatar update.
                    if (!force) { state.lastHandle = handle; state.nextSend = now.AddMinutes(30); }
                    else state.nextCheck = DateTime.MinValue;
                    return Convert.ToBase64String(stream.ToArray());
                }
            }
        } catch (Exception) { state.nextCheck = now.AddSeconds(60); return null; }
    }
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
                    if (SteamAvatarRequests.TryParseCommand(line, out requested) && new CSteamID(requested).BIndividualAccount()) {
                        if (!historicalAvatars.Enqueue(requested)) lock (rejectedAvatars) {
                            if (rejectedAvatars.Count < 32) rejectedAvatars.Enqueue(requested);
                        }
                    } else if (UInt64.TryParse(line, out requested)) lock (profileRequests) { profileRequests.Enqueue(requested); }
                } } catch (IOException) { }
            });
            inputThread.IsBackground = true;
            inputThread.Start();
            var parent = Process.GetProcessById(Int32.Parse(args[1]));
            var seedCandidates = new List<ulong>();
            if (args.Length == 4) {
                foreach (string token in args[3].Split(',')) {
                    ulong seed;
                    if (UInt64.TryParse(token, out seed) && seed >= 0x0110000100000000UL) seedCandidates.Add(seed);
                }
            }
            var logTail = new SteamLogTail();
            DateTime started = DateTime.Now;
            while (!parent.HasExited && Process.GetProcessesByName("eldenring").Length > 0) {
                SteamAPI.RunCallbacks();
                lock (rejectedAvatars) {
                    while (rejectedAvatars.Count > 0)
                        Emit(new { type="avatar", id=rejectedAvatars.Dequeue().ToString(), state="unavailable" });
                }
                historicalAvatars.Tick(DateTime.UtcNow,
                    id => AvatarUpdate(new CSteamID(id), id, DateTime.UtcNow, true),
                    (id, image) => {
                        if (image == null) {
                            bool loggedOn = false;
                            try { loggedOn = SteamUser.BLoggedOn(); } catch (Exception) { }
                            Emit(new { type="avatar", id=id.ToString(), state=SteamAvatarRequests.MissingImageState(loggedOn) });
                        }
                        else Emit(new { type="avatar", id=id.ToString(), state="ready", avatar_png=image });
                    });
                lock (profileRequests) {
                    while (profileRequests.Count > 0) {
                        ulong id = profileRequests.Dequeue();
                        var requested = new CSteamID(id);
                        if (requested.BIndividualAccount()) { try { SteamFriends.ActivateGameOverlayToUser("steamid", requested); } catch (Exception) { } }
                    }
                }
                SteamFriends.SendClanChatMessage(new CSteamID(0), "");
                if (!logTail.Poll(args[0],
                        line => SteamLogEvents.ProcessLine(line, candidates, DateTime.UtcNow),
                        () => candidates.Clear())) {
                    foreach (ulong netId in registered) ETWPingMonitor.Unregister(netId);
                    registered.Clear();
                    Emit(new { status="waiting_log" }); Thread.Sleep(2000); continue;
                }
                // Seeds came from the just-running helper. Replay of older log
                // events must not erase them before Steam can verify them.
                foreach (ulong seed in seedCandidates) candidates[seed] = DateTime.UtcNow;
                seedCandidates.Clear();
                var peers = new List<object>();
                // Stop retaining ping samples once an endpoint is no longer
                // connected: a later session may reuse the same IP and port.
                var activeNetIds = new HashSet<ulong>();
                foreach (var id in candidates.Keys.ToList()) {
                    var sid = new CSteamID(id);
                    var identity = new SteamNetworkingIdentity(); identity.SetSteamID(sid);
                    SteamNetConnectionInfo_t info; SteamNetConnectionRealTimeStatus_t realtime;
                    bool connected = false;
                    bool established = false;
                    realtime = new SteamNetConnectionRealTimeStatus_t();
                    try {
                        var state = SteamNetworkingMessages.GetSessionConnectionInfo(ref identity, out info, out realtime);
                        connected = state == ESteamNetworkingConnectionState.k_ESteamNetworkingConnectionState_Connected || state == ESteamNetworkingConnectionState.k_ESteamNetworkingConnectionState_Connecting;
                        established = state == ESteamNetworkingConnectionState.k_ESteamNetworkingConnectionState_Connected;
                    } catch (Exception) { }
                    P2PSessionState_t legacy = new P2PSessionState_t();
                    bool old = false;
                    try { old = !connected && SteamNetworking.GetP2PSessionState(sid, out legacy) && legacy.m_eP2PSessionError == 0 && (legacy.m_bConnecting != 0 || legacy.m_bConnectionActive != 0); } catch (Exception) { }
                    if (connected || old) {
                        candidates[id] = DateTime.UtcNow;
                        // The tracker publishes at most 16 peers. Do not mark
                        // avatars for other peers as sent: they may move into
                        // the visible set on the very next update.
                        if (peers.Count >= 16) continue;
                        string name = SteamFriends.GetFriendPersonaName(sid);
                        bool? steamFriend = null;
                        try {
                            if (SteamUser.BLoggedOn())
                                steamFriend = SteamFriends.GetFriendRelationship(sid) == EFriendRelationship.k_EFriendRelationshipFriend;
                        } catch (Exception) { /* An unavailable relationship is not a negative result. */ }
                        int? ping = connected && realtime.m_nPing >= 0 ? (int?)realtime.m_nPing : null;
                        double? averagePing = null, jitter = null, quality = null;
                        if (established && !Single.IsNaN(realtime.m_flConnectionQualityLocal) &&
                            realtime.m_flConnectionQualityLocal >= 0 && realtime.m_flConnectionQualityLocal <= 1)
                            quality = realtime.m_flConnectionQualityLocal;
                        string address = null;
                        if (old && legacy.m_nRemoteIP != 0) address = new IPAddress(BitConverter.GetBytes(legacy.m_nRemoteIP).Reverse().ToArray()).ToString();
                        if (old && pingMode == "active" && legacy.m_nRemoteIP != 0 && legacy.m_nRemotePort != 0) {
                            byte[] ip = BitConverter.GetBytes(legacy.m_nRemoteIP).Reverse().ToArray();
                            ulong netId = (ulong)legacy.m_nRemotePort << 32 | BitConverter.ToUInt32(ip, 0);
                            activeNetIds.Add(netId);
                            if (registered.Add(netId)) ETWPingMonitor.Register(netId);
                            double measured = ETWPingMonitor.GetPing(netId);
                            if (measured >= 0 && measured < 60000) ping = (int)Math.Round(measured);
                            double average, spread;
                            if (ETWPingMonitor.TryGetStatistics(netId, out average, out spread)) {
                                averagePing = Math.Round(average, 1);
                                jitter = Math.Round(spread, 1);
                            }
                        }
                        string avatarPng = AvatarUpdate(sid, id, DateTime.UtcNow);
                        peers.Add(new { id=id.ToString(), name=String.IsNullOrWhiteSpace(name) ? id.ToString() : name, ping=ping,
                            average_ping=averagePing, jitter=jitter, quality=quality, avatar_png=avatarPng, steam_friend=steamFriend,
                            ip=address, relay=old && legacy.m_bUsingRelay != 0 });
                    } else if ((DateTime.UtcNow - candidates[id]).TotalSeconds > 5) candidates.Remove(id);
                }
                foreach (ulong netId in registered.Except(activeNetIds).ToList()) {
                    ETWPingMonitor.Unregister(netId);
                    registered.Remove(netId);
                }
                bool logging = File.GetLastWriteTime(args[0]) >= started.AddSeconds(-2);
                Emit(new { status=(logging || peers.Count > 0) ? "active" : "waiting_log", ping_mode=pingMode, peers=peers });
                Thread.Sleep(1000);
            }
            SteamAPI.Shutdown(); Emit(new { status="game_closed" });
        } catch (Exception) { try { Emit(new { status="helper_error" }); } catch (Exception) { } }
        finally { if (ETWPingMonitor.Running) ETWPingMonitor.Stop(); }
    }
}

