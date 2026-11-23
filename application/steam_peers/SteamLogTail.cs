// Read Steam's IPC log without changing it or reading game memory.
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Win32.SafeHandles;

public static class SteamLogEvents {
    static readonly Regex Ids = new Regex(@"\[U:1:(\d+)\]", RegexOptions.Compiled);

    public static void ProcessLine(string line, IDictionary<ulong, DateTime> candidates, DateTime now) {
        if (line.IndexOf("eldenring", StringComparison.OrdinalIgnoreCase) < 0) return;
        if (line.Contains("LeaveLobby")) { candidates.Clear(); return; }
        Match match = Ids.Match(line);
        ulong number;
        if (!match.Success || !UInt64.TryParse(match.Groups[1].Value, out number) || number > UInt32.MaxValue) return;
        ulong id = 0x0110000100000000UL + number;
        if (line.Contains("BeginAuthSession")) candidates[id] = now;
        else if (line.Contains("EndAuthSession")) candidates.Remove(id);
    }
}

public sealed class SteamLogTail {
    const int MaxLineBytes = 64 * 1024;
    const int AnchorBytes = 64;
    readonly long initialBytes;
    readonly List<byte> pending = new List<byte>();
    long offset;
    bool initialized, droppingLine;
    string identity;
    byte[] anchor = new byte[0];

    [StructLayout(LayoutKind.Sequential)]
    struct FileInformation {
        public uint attributes, creationLow, creationHigh, accessLow, accessHigh, writeLow, writeHigh;
        public uint volume, sizeHigh, sizeLow, links, indexHigh, indexLow;
    }
    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool GetFileInformationByHandle(SafeFileHandle file, out FileInformation information);

    public SteamLogTail(long initialBytes = 8L * 1024 * 1024) {
        if (initialBytes <= 0) throw new ArgumentOutOfRangeException("initialBytes");
        this.initialBytes = initialBytes;
    }

    static string Identity(FileStream stream, string path) {
        FileInformation info;
        if (GetFileInformationByHandle(stream.SafeFileHandle, out info))
            return info.volume.ToString("x") + ":" + info.indexHigh.ToString("x") + ":" + info.indexLow.ToString("x");
        return "creation:" + File.GetCreationTimeUtc(path).Ticks.ToString();
    }

    bool AnchorMatches(FileStream stream) {
        if (anchor.Length == 0) return true;
        stream.Seek(offset - anchor.Length, SeekOrigin.Begin);
        for (int i = 0; i < anchor.Length; i++) if (stream.ReadByte() != anchor[i]) return false;
        return true;
    }

    void SaveAnchor(FileStream stream) {
        int count = (int)Math.Min(offset, AnchorBytes);
        anchor = new byte[count];
        stream.Seek(offset - count, SeekOrigin.Begin);
        int read = 0;
        while (read < count) {
            int n = stream.Read(anchor, read, count - read);
            if (n == 0) { anchor = new byte[0]; return; }
            read += n;
        }
    }

    void Consume(byte value, Action<string> onLine) {
        if (value == 10) {
            if (!droppingLine) {
                int count = pending.Count;
                if (count > 0 && pending[count - 1] == 13) count--;
                onLine(Encoding.UTF8.GetString(pending.ToArray(), 0, count));
            }
            pending.Clear();
            droppingLine = false;
        } else if (!droppingLine) {
            if (pending.Count >= MaxLineBytes) { pending.Clear(); droppingLine = true; }
            else pending.Add(value);
        }
    }

    // Returns false when the log is temporarily absent or locked. Partial
    // lines are retained until their newline arrives and never parsed twice.
    public bool Poll(string path, Action<string> onLine, Action onReset) {
        try {
            using (var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete)) {
                string currentIdentity = Identity(stream, path);
                long length = stream.Length;
                bool reset = initialized && (currentIdentity != identity || length < offset || !AnchorMatches(stream));
                if (!initialized || reset) {
                    if (reset) onReset();
                    pending.Clear();
                    offset = Math.Max(0, length - initialBytes);
                    droppingLine = false;
                    if (offset > 0) {
                        stream.Seek(offset - 1, SeekOrigin.Begin);
                        droppingLine = stream.ReadByte() != 10;
                    }
                    identity = currentIdentity;
                    initialized = true;
                }
                stream.Seek(offset, SeekOrigin.Begin);
                byte[] buffer = new byte[16384];
                while (offset < length) {
                    int count = stream.Read(buffer, 0, (int)Math.Min(buffer.Length, length - offset));
                    if (count == 0) break;
                    for (int i = 0; i < count; i++) Consume(buffer[i], onLine);
                    offset += count;
                }
                SaveAnchor(stream);
                return true;
            }
        } catch (FileNotFoundException) { return false; }
          catch (DirectoryNotFoundException) { return false; }
          catch (IOException) { return false; }
    }
}
