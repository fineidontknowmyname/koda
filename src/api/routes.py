from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from io import BytesIO
from src.schemas.plan import GeneratePlanRequest
from src.api.dependencies import get_orchestrator
from src.core.orchestrator import PlanOrchestrator
from src.reporting.pdf_architect import pdf_architect

api_router = APIRouter()

@api_router.post("/generate-plan", summary="Generate a 4-week fitness PDF")
async def generate_plan_endpoint(
    request: GeneratePlanRequest,
    orchestrator: PlanOrchestrator = Depends(get_orchestrator)
):
    try:
        # 1. Orchestrate the Logic
        plan = await orchestrator.generate_plan(
            user_profile=request.user_profile,
            transcript_text=request.transcript_text
        )
        
        # 2. Render PDF
        pdf_bytes = pdf_architect.render_plan(plan)
        
        # 3. Stream Response
        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=koda_plan.pdf"}
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Log this in production
        print(f"Server Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error processing plan.")
