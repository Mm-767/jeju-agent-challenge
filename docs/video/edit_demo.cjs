// record_demo.cjs 다음에 실행(badge.png는 「4배속」 표시 그림, ffmpeg에 글자 필터가 없어 그림으로 겹친다): AI 대기 구간(marks.json의 think_start~think_end)을 4배속으로 줄여 build/video/demo.mp4를 만든다.
const { execFileSync } = require("child_process");
const path = require("path");
const fs = require("fs");

const DIR = path.resolve(__dirname, "../../build/video");
const m = JSON.parse(fs.readFileSync(path.join(DIR, "marks.json"), "utf8"));
const SPEED = 4;
const graph = [
  `[0:v]trim=0:${m.think_start},setpts=PTS-STARTPTS[a]`,
  `[0:v]trim=${m.think_start}:${m.think_end},setpts=(PTS-STARTPTS)/${SPEED}[b0]`,
  `[b0][1:v]overlay=W-w-60:110[b]`,
  `[0:v]trim=${m.think_end},setpts=PTS-STARTPTS[c]`,
  `[a][b][c]concat=n=3:v=1:a=0,fps=30,format=yuv420p[v]`,
].join(";");
execFileSync("ffmpeg", ["-v", "error", "-y", "-i", path.join(DIR, "raw.webm"), "-i", path.join(DIR, "badge.png"), "-filter_complex", graph, "-map", "[v]",
  "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-movflags", "+faststart", path.join(DIR, "demo.mp4")], { stdio: "inherit" });
console.log("demo.mp4 완성");
