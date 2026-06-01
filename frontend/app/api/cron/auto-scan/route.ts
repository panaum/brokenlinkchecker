import { NextRequest, NextResponse } from "next/server";
import { DashboardSite } from "@/types";

export async function POST(req: NextRequest) {
  // 1. Verify CRON_SECRET
  const authHeader = req.headers.get("authorization");
  const cronSecret = process.env.CRON_SECRET;

  if (cronSecret && authHeader !== `Bearer ${cronSecret}`) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  try {
    const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";

    // 2. Fetch all sites
    const dashboardRes = await fetch(`${backendUrl}/dashboard`, {
      cache: "no-store",
    });
    
    if (!dashboardRes.ok) {
      throw new Error("Failed to fetch sites from backend");
    }

    const { sites } = (await dashboardRes.json()) as { sites: DashboardSite[] };
    
    if (!sites || sites.length === 0) {
      return NextResponse.json({ message: "No sites to scan", triggered: 0 });
    }

    const now = Date.now();
    let triggeredCount = 0;

    // 3. Determine which sites need scanning based on freq and last_scanned_at
    const scanPromises = sites.map(async (site) => {
      let shouldScan = false;
      const freq = site.freq || "Daily";
      
      if (!site.last_scanned_at) {
        shouldScan = true;
      } else {
        const lastScanned = new Date(site.last_scanned_at).getTime();
        const diffHours = (now - lastScanned) / (1000 * 60 * 60);

        if (freq === "Daily" && diffHours >= 24) shouldScan = true;
        if (freq === "Weekly" && diffHours >= 168) shouldScan = true; // 7 days
        if (freq === "Monthly" && diffHours >= 720) shouldScan = true; // 30 days
      }

      if (shouldScan) {
        triggeredCount++;
        // Trigger the scan asynchronously (don't await its completion to avoid Vercel timeouts)
        fetch(`${backendUrl}/scan?url=${encodeURIComponent(site.url)}`).catch(err => 
          console.error(`Auto-scan failed for ${site.url}:`, err)
        );
      }
    });

    // We don't await the actual scans to finish, just the synchronous checks
    await Promise.all(scanPromises);

    return NextResponse.json({
      status: "success",
      message: `Triggered ${triggeredCount} automated scans`,
      totalSites: sites.length
    });

  } catch (error: any) {
    console.error("Cron auto-scan error:", error);
    return NextResponse.json({ error: error.message }, { status: 500 });
  }
}
