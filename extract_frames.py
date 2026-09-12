import imageio_ffmpeg, subprocess, os

FF = imageio_ffmpeg.get_ffmpeg_exe()
os.makedirs(r'D:\work\fairy-pet\ref_video\frames_boot', exist_ok=True)
os.makedirs(r'D:\work\fairy-pet\ref_video\frames_idle', exist_ok=True)

# 先探测时长/分辨率
for name in ['boot', 'idle']:
    r = subprocess.run([FF, '-i', rf'D:\work\fairy-pet\ref_video\{name}.f30080.mp4'], capture_output=True, text=True)
    line = [l for l in r.stderr.split('\n') if 'Video:' in l]
    print(name, line[0].strip() if line else 'no video stream')

# boot: 前 80 秒，每 1 秒 1 帧
subprocess.run([FF, '-y', '-ss', '0', '-t', '80', '-i', r'D:\work\fairy-pet\ref_video\boot.f30080.mp4',
                '-vf', 'fps=1,scale=960:-1', r'D:\work\fairy-pet\ref_video\frames_boot\f%03d.jpg'],
               capture_output=True)
# idle: 全片每 0.5 秒 1 帧
subprocess.run([FF, '-y', '-i', r'D:\work\fairy-pet\ref_video\idle.f30080.mp4',
                '-vf', 'fps=2,scale=960:-1', r'D:\work\fairy-pet\ref_video\frames_idle\f%03d.jpg'],
               capture_output=True)
print('boot frames:', len(os.listdir(r'D:\work\fairy-pet\ref_video\frames_boot')))
print('idle frames:', len(os.listdir(r'D:\work\fairy-pet\ref_video\frames_idle')))
