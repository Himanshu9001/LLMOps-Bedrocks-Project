FROM public.ecr.aws/lambda/python:3.12-arm64

RUN dnf install -y gcc gcc-c++ && dnf clean all

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py ${LAMBDA_TASK_ROOT}/

CMD ["handler.lambda_handler"]