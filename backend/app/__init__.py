from fastapi import FastAPI
from .routers import auth, users, contractors, contracts, purchases, payments, feo_categories, dashboard, subsidies, products, purchase_files, documents, publications, subsidy_approvers, responsible_persons
from .models import platform_publication  # ensure table is registered

app = FastAPI(title="VSKS CRM API", version="1.0.0")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(contractors.router)
app.include_router(contracts.router)
app.include_router(purchases.router)
app.include_router(payments.router)
app.include_router(feo_categories.router)
app.include_router(dashboard.router)
app.include_router(subsidies.router)
app.include_router(products.router)
app.include_router(purchase_files.router)
app.include_router(documents.router)
app.include_router(publications.router)
app.include_router(subsidy_approvers.router)
app.include_router(responsible_persons.router)