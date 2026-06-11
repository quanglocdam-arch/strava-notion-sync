# 🏃 Strava → Notion Auto Sync

Script Python + GitHub Actions tự động đồng bộ các buổi chạy từ Strava vào Notion mỗi 4 tiếng.

---

## Cài đặt (một lần duy nhất)

### Bước 1 — Lấy Strava credentials

1. Vào **https://www.strava.com/settings/api**
2. Tạo app mới (hoặc dùng app cũ):
   - **Application Name**: bất kỳ (vd: `notion-sync`)
   - **Authorization Callback Domain**: `localhost`
3. Ghi lại **Client ID** và **Client Secret**

**Lấy Refresh Token:**

Mở URL sau trong trình duyệt (thay `YOUR_CLIENT_ID`):

```
https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http://localhost&approval_prompt=force&scope=activity:read_all
```

Sau khi cho phép, trình duyệt chuyển về `localhost` (báo lỗi — bình thường).
Copy phần `code=XXXX` từ URL, rồi chạy lệnh sau (thay 3 giá trị):

```bash
curl -X POST https://www.strava.com/oauth/token \
  -d client_id=YOUR_CLIENT_ID \
  -d client_secret=YOUR_CLIENT_SECRET \
  -d code=CODE_VỪA_COPY \
  -d grant_type=authorization_code
```

Response trả về JSON — lấy giá trị **`refresh_token`**.

---

### Bước 2 — Lấy Notion credentials

1. Vào **https://www.notion.so/my-integrations**
2. Tạo integration mới:
   - Name: `strava-sync`
   - Workspace: chọn workspace của bạn
3. Copy **Internal Integration Token** (bắt đầu bằng `secret_...`)

**Lấy Notion Page ID:**

1. Mở trang Notion muốn tạo database trong đó
2. URL có dạng: `https://notion.so/ten-trang-**abc123def456...**`
3. Copy 32 ký tự cuối (đó là Page ID)
4. Vào trang đó → nhấn `...` góc trên phải → **"Add connections"** → chọn integration `strava-sync`

---

### Bước 3 — Tạo GitHub repo và thêm Secrets

1. Tạo repo mới trên GitHub (có thể để **Private**)
2. Upload 3 file: `sync.py`, `requirements.txt`, và folder `.github/`
3. Vào **Settings → Secrets and variables → Actions → New repository secret**

Thêm 5 secrets sau:

| Secret name            | Giá trị                        |
|------------------------|-------------------------------|
| `STRAVA_CLIENT_ID`     | Client ID từ Strava           |
| `STRAVA_CLIENT_SECRET` | Client Secret từ Strava       |
| `STRAVA_REFRESH_TOKEN` | Refresh token vừa lấy         |
| `NOTION_TOKEN`         | Token `secret_...` từ Notion  |
| `NOTION_PAGE_ID`       | Page ID của trang Notion       |

---

### Bước 4 — Chạy thử

Vào tab **Actions** trên GitHub repo → chọn workflow **"Strava → Notion Sync"** → nhấn **"Run workflow"**.

Nếu thành công, database **🏃 Strava Runs** sẽ xuất hiện trong trang Notion của bạn.

---

## Lịch chạy tự động

Workflow chạy mỗi **4 tiếng** theo UTC. Bạn có thể chỉnh trong `.github/workflows/sync.yml`:

```yaml
- cron: "0 */4 * * *"   # mỗi 4 tiếng
- cron: "0 */2 * * *"   # mỗi 2 tiếng
- cron: "0 20 * * *"    # mỗi ngày 3h sáng GMT+7
```

---

## Database columns

| Cột              | Kiểu    | Nội dung                      |
|------------------|---------|-------------------------------|
| Name             | Title   | Tên buổi chạy                 |
| Date             | Date    | Ngày chạy                     |
| Distance (km)    | Number  | Quãng đường (km)              |
| Duration         | Text    | Thời gian (hh:mm:ss)          |
| Pace             | Text    | Tốc độ trung bình (/km)       |
| Elevation (m)    | Number  | Độ leo dốc (mét)              |
| Heart Rate (bpm) | Number  | Nhịp tim trung bình           |
| Strava Link      | URL     | Link buổi chạy trên Strava    |

---

## Ghi chú

- Script tự dedup — buổi chạy đã có trong Notion sẽ bị bỏ qua, không bị thêm 2 lần.
- GitHub Actions free tier cho phép 2.000 phút/tháng — chạy mỗi 4 tiếng tốn khoảng 45 phút/tháng, hoàn toàn miễn phí.
- Refresh token Strava không hết hạn (trừ khi thu hồi quyền trong app).
